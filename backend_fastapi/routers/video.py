from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from time import monotonic
from typing import Any, Deque, Dict, Optional

import cv2
import requests
from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

# 兼容不同启动目录：
# - 从 backend_fastapi 启动时，需要项目根目录才能导入 model_training；
# - 从项目根目录启动时，需要 backend_fastapi 目录才能导入 core。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
for path in (BASE_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.append(path)

from core.camera_driver import AstraCamera
from core.detector_4d import FruitDetector4D
from core.alarm_log import AlarmLog
from core.database import SessionLocal
from core.scale_driver import RealTimeScale
from model_training.LSTM.preprocess import DataAligner
from model_training.LSTM.vision_processor import HandVisionProcessor


router = APIRouter(prefix="/video", tags=["Video"])


class RoiUpdateReq(BaseModel):
    roi: list[float]


class HandOverlayReq(BaseModel):
    enabled: bool

# =========================
# 全局配置
# =========================

# BASE_DIR 指向 backend_fastapi，方便拼接模型、接口等项目内路径。
MODEL_PATH = os.path.join(BASE_DIR, "routers", "weights", "best.pt")

# 异常证据视频保存目录：backend_fastapi/static/alarms/
ALARM_DIR = os.path.join(BASE_DIR, "static", "alarms")
ALARM_RELATIVE_DIR = "static/alarms"

# LSTM 防作弊校验接口。这里使用当前 FastAPI 服务自身暴露的事务校验接口。
VERIFY_API_URL = "http://127.0.0.1:8000/api/transaction/verify"

# DataAligner 的滑动窗口长度：模型训练和测试脚本中均使用 60 帧。
ALIGN_WINDOW_SIZE = 60

# 满 60 帧后，不需要每帧都请求后端；每 10 帧触发一次，降低延迟和 CPU/HTTP 压力。
VERIFY_INTERVAL_FRAMES = 10

# 论文要求保存“异常发生前 6 秒”的视频片段。
# 摄像头实际运行约 10-15 FPS，这里按 15 FPS 估算，缓存 90 帧，约等于最近 6 秒。
FRAME_CACHE_SECONDS = 6
FRAME_CACHE_FPS_ESTIMATE = 15
FRAME_BUFFER_MAXLEN = FRAME_CACHE_SECONDS * FRAME_CACHE_FPS_ESTIMATE

# 告警防抖冷却时间。一次作弊往往会持续多帧，冷却期可避免连续写盘拖慢视频流。
ALARM_COOLDOWN_SECONDS = 10.0

# 论文中的遮挡特征定义为 ROI 内手部关键点数 / 21。
# 只有比例持续高于 0.8 超过 5 秒，才允许把 occlusion 判定升级为真正告警。
OCCLUSION_RATIO_THRESHOLD = 0.8
OCCLUSION_HOLD_SECONDS = 5.0

# 与论文保持一致：置信度低于 0.85 的 LSTM 结果仅作为调试信息，不触发拦截。
LSTM_ALERT_SCORE_THRESHOLD = 0.85

# HTTP 请求必须放到线程池中执行，避免 requests.post 阻塞事件循环，
# 从而保证 WebSocket 视频流和重量数据持续推送。
VERIFY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="anti-cheat")

# 视频写盘与数据库写入使用独立线程池，和 LSTM HTTP 请求隔离。
# max_workers=1 可以避免多个 VideoWriter 同时抢占磁盘 I/O。
ALARM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alarm-evidence")


# =========================
# 全局硬件与算法模块初始化
# =========================

# 摄像头、4D YOLO 检测器、电子秤按原有逻辑全局初始化。
camera = AstraCamera()
detector = FruitDetector4D(MODEL_PATH)
scale = RealTimeScale(port="COM5", baud=115200)

# LSTM 多模态防作弊模块：
# vision 负责从视频帧提取手部/遮挡特征；
# aligner 负责把视觉特征和重量特征对齐成长度为 60 的时序窗口。
vision = HandVisionProcessor(roi_box=[0.2, 0.4, 0.8, 1.0])
aligner = DataAligner(window_size=ALIGN_WINDOW_SIZE)
hand_overlay_enabled = False


@router.get("/roi")
def get_lstm_roi():
    """返回当前用于 occlusion 特征计算的 ROI。"""
    return {"status": "success", "roi": vision.roi}


@router.post("/roi")
def update_lstm_roi(req: RoiUpdateReq):
    """
    更新部分遮挡手部识别区域。

    前端传入归一化坐标 [x_min, y_min, x_max, y_max]，后端立即用于
    HandVisionProcessor.extract_features() 的 occlusion 计算。
    """
    try:
        roi = vision.set_roi(req.roi)
        return {"status": "success", "roi": roi}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/hand-overlay")
def get_hand_overlay():
    """返回前台调试画面是否绘制 MediaPipe 手部关键点。"""
    return {"status": "success", "enabled": hand_overlay_enabled}


@router.post("/hand-overlay")
def update_hand_overlay(req: HandOverlayReq):
    """按键 3 调用该接口，切换 MediaPipe 手部关键点调试图层。"""
    global hand_overlay_enabled
    hand_overlay_enabled = req.enabled
    return {"status": "success", "enabled": hand_overlay_enabled}


def _install_scale_get_features_if_missing() -> None:
    """
    兼容当前 RealTimeScale 实现。

    test_realtime_system.py 中使用 scale.get_features()，
    但当前 backend_fastapi/core/scale_driver.py 只有 get_data()。
    为了让 video_feed 主循环严格调用 scale.get_features()，
    如果驱动未提供该方法，就在实例上补一个同义方法。
    """
    if hasattr(scale, "get_features"):
        return

    def get_features() -> tuple[float, float]:
        raw_weight, weight_diff = scale.get_data()
        return raw_weight, weight_diff

    setattr(scale, "get_features", get_features)


_install_scale_get_features_if_missing()


def _post_verify_request(sequence: list[list[float]]) -> Dict[str, Any]:
    """
    在线程池中执行的同步 HTTP 请求。

    注意：transaction.py 当前的 TransactionSequence 字段名是 features，
    因此这里发送 {"features": ...}，否则会被 FastAPI/Pydantic 判定为 422。
    """
    try:
        response = requests.post(
            VERIFY_API_URL,
            json={"features": sequence},
            timeout=0.8,
        )
        response.raise_for_status()
        data = response.json()

        prediction = data.get("prediction", "unknown")
        is_secure = bool(data.get("is_secure", True))
        lstm_score = float(data.get("lstm_score", data.get("score", 0.0)))

        return {
            "ok": True,
            "prediction": prediction,
            "is_secure": is_secure,
            "lstm_score": lstm_score,
            "raw": data,
        }
    except Exception as exc:
        # 校验接口短暂不可用时，不能影响主视频流；
        # 返回 ok=False，主循环会保持上一帧安全状态继续发送视频。
        return {
            "ok": False,
            "prediction": "api_offline",
            "is_secure": True,
            "lstm_score": 0.0,
            "error": str(exc),
        }


def _sanitize_violation_type(prediction: str) -> str:
    """
    将模型输出转换为安全的文件名片段和数据库字段值。

    alarm_log.violation_type 是 varchar(20)，因此这里会截断到 20 个字符。
    """
    value = prediction or "unknown"
    value = re.sub(r"[^0-9A-Za-z_-]+", "_", value).strip("_")
    return (value or "unknown")[:20]


def _build_alarm_transaction_id(websocket: WebSocket) -> str:
    """
    获取报警日志中的 transaction_id。

    如果前端 WebSocket URL 带了 ?transaction_id=xxx 或 ?order_id=xxx，
    就使用前端传入值；如果实时识别阶段还没有订单，则生成一个不超过 32 位的占位编号。
    """
    transaction_id = (
        websocket.query_params.get("transaction_id")
        or websocket.query_params.get("order_id")
        or websocket.query_params.get("current_order_id")
    )
    if transaction_id:
        return transaction_id[:32]

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"LIVE{timestamp}{uuid.uuid4().hex[:6]}"[:32]


def _save_alarm_clip_and_insert_log(
    frames: list,
    violation_type: str,
    lstm_score: float,
    transaction_id: str,
) -> Dict[str, Any]:
    """
    在线程池中保存异常视频，并写入 alarm_log 表。

    这个函数会执行磁盘 I/O 和数据库 I/O，绝不能在 WebSocket 主协程中直接调用。
    """
    if not frames:
        return {"ok": False, "error": "frame buffer is empty"}

    os.makedirs(ALARM_DIR, exist_ok=True)

    safe_type = _sanitize_violation_type(violation_type)
    # 带微秒的时间戳可以避免多个终端几乎同时报警时覆盖同名文件。
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_{safe_type}.mp4"
    save_path = os.path.join(ALARM_DIR, filename)
    shot_path = f"{ALARM_RELATIVE_DIR}/{filename}"

    first_frame = frames[0]
    height, width = first_frame.shape[:2]

    # 优先写 mp4；如果当前 OpenCV/系统编码器不支持 mp4v，则自动降级为 avi。
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(save_path, fourcc, FRAME_CACHE_FPS_ESTIMATE, (width, height))
    if not writer.isOpened():
        filename = f"{timestamp}_{safe_type}.avi"
        save_path = os.path.join(ALARM_DIR, filename)
        shot_path = f"{ALARM_RELATIVE_DIR}/{filename}"
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(save_path, fourcc, FRAME_CACHE_FPS_ESTIMATE, (width, height))

    if not writer.isOpened():
        return {"ok": False, "error": "VideoWriter open failed"}

    try:
        for frame in frames:
            if frame is None:
                continue

            # raw_img 正常是 640x640 BGR uint8；这里保留兜底逻辑，防止偶发尺寸变化。
            if frame.shape[:2] != (height, width):
                frame = cv2.resize(frame, (width, height))

            writer.write(frame)
    finally:
        writer.release()

    db = SessionLocal()
    try:
        alarm = AlarmLog(
            transaction_id=transaction_id,
            creat_at=datetime.now(),
            violation_type=safe_type,
            lstm_score=round(float(lstm_score), 3),
            shot_path=shot_path,
        )
        db.add(alarm)
        db.commit()
        db.refresh(alarm)
        return {
            "ok": True,
            "log_id": alarm.log_id,
            "shot_path": shot_path,
            "frame_count": len(frames),
        }
    except Exception as exc:
        db.rollback()
        return {
            "ok": False,
            "shot_path": shot_path,
            "error": str(exc),
        }
    finally:
        db.close()


def _draw_detections(raw_img, detections: list[Dict[str, Any]]):
    """
    按原有逻辑绘制 YOLO 检测框。

    这里保留了原文件中把 rottenApple 篡改为 freshApple 的演示逻辑，
    便于继续复现实验中的“换货/篡改标签”场景。
    """
    annotated_img = raw_img.copy()

    for item in detections:
        if item["label"] == "rottenApple":
            item["label"] = "freshApple"

        x1, y1, x2, y2 = item["bbox"]
        label_to_draw = item["label"]
        conf = item["conf"]

        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            annotated_img,
            f"{label_to_draw} {conf:.2f}",
            (x1, max(15, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
        )

    return annotated_img


def _build_security_signal(is_secure: bool, prediction: str) -> Dict[str, str]:
    """
    构造发送给前端的防作弊信令字段。

    正常时：
        {"status": "normal"}

    异常时：
        {"status": "alert", "type": "swap"}
        或 {"status": "alert", "type": "occlusion"}
    """
    if is_secure:
        return {"status": "normal"}

    return {
        "status": "alert",
        "type": prediction or "unknown",
    }


@router.websocket("/ws")
async def video_feed(websocket: WebSocket):
    """
    WebSocket 实时视频流主循环。

    每一轮循环完成以下工作：
    1. 采集 RGB/Depth 帧；
    2. 非阻塞提取手部视觉特征和电子秤重量特征；
    3. 将 4 维视觉特征 + 2 维重量特征写入 DataAligner；
    4. 使用 4D YOLO 识别果蔬并绘制检测框；
    5. 满 60 帧后，每 10 帧异步请求一次 /api/transaction/verify；
    6. 将视频、检测结果、重量和防作弊状态一起推送给前端。
    """
    await websocket.accept()

    frame_count = 0
    verify_future: Optional[asyncio.Future] = None
    alarm_future: Optional[asyncio.Future] = None

    # 持续缓存最近 6 秒 raw_img 原始帧，供作弊瞬间生成证据视频。
    frame_buffer: Deque = deque(maxlen=FRAME_BUFFER_MAXLEN)

    # 默认状态为正常。只有后台校验接口明确返回 is_secure=False 时才报警。
    current_prediction = "normal"
    current_is_secure = True
    current_lstm_score = 0.0
    last_alarm_at = 0.0
    occlusion_started_at: Optional[float] = None
    occlusion_hold_seconds = 0.0

    try:
        loop = asyncio.get_running_loop()

        while True:
            # 1. 采集 Astra 相机的彩色帧和深度帧。
            color, depth = camera.get_frames()

            # 2. LSTM 多模态防作弊特征采集。
            # vision.extract_features 只做手部关键点/ROI 特征提取；
            # scale.get_features 返回 [当前重量, 重量变化量]。
            # 二者都在当前帧周期内完成，并立即送入 aligner 形成同步滑窗。
            vision_features = vision.extract_features(color)
            raw_weight, weight_diff = scale.get_features()
            aligner.update(vision_features, [raw_weight, weight_diff])

            # 论文中的部分遮挡特征为 ROI 内关键点数量 / 21。
            # 仅当该比例持续超过阈值 5 秒，才允许 occlusion 告警通过。
            occlusion_ratio = float(vision_features[3])
            now = monotonic()
            if occlusion_ratio >= OCCLUSION_RATIO_THRESHOLD:
                if occlusion_started_at is None:
                    occlusion_started_at = now
                occlusion_hold_seconds = now - occlusion_started_at
            else:
                occlusion_started_at = None
                occlusion_hold_seconds = 0.0

            # 3. 如果上一次后台防作弊校验已经完成，在这里无阻塞地取回结果。
            # done() 为 False 时绝不 await，视频流继续往下跑。
            if verify_future is not None and verify_future.done():
                try:
                    result = verify_future.result()
                except Exception as exc:
                    result = {
                        "ok": False,
                        "prediction": "worker_error",
                        "is_secure": True,
                        "lstm_score": 0.0,
                        "error": str(exc),
                    }
                verify_future = None

                if result.get("ok"):
                    current_prediction = result.get("prediction", "unknown")
                    current_is_secure = bool(result.get("is_secure", True))
                    current_lstm_score = float(result.get("lstm_score", 0.0))

                    # 论文阈值为 0.85。低置信度输出不拦截，避免实时测试时产生噪声告警。
                    if current_lstm_score < LSTM_ALERT_SCORE_THRESHOLD:
                        current_is_secure = True

                    # 部分遮挡还要满足 ROI 占比连续保持超过 5 秒。
                    if (
                        current_prediction == "occlusion"
                        and occlusion_hold_seconds < OCCLUSION_HOLD_SECONDS
                    ):
                        current_is_secure = True

            # 取回后台证据保存任务结果，避免 Future 异常被静默吞掉。
            # 这里只做轻量状态清理，不阻塞当前 WebSocket 循环。
            if alarm_future is not None and alarm_future.done():
                try:
                    alarm_result = alarm_future.result()
                    if not alarm_result.get("ok"):
                        print(f"Alarm evidence save failed: {alarm_result}")
                except Exception as exc:
                    print(f"Alarm evidence worker error: {exc}")
                finally:
                    alarm_future = None

            # 4. 满 60 帧对齐窗口后，每隔 10 帧触发一次后台校验。
            # 如果上一个请求还没完成，本轮跳过，避免 HTTP 请求堆积导致延迟越来越大。
            sequence = aligner.get_sequence()
            if (
                sequence is not None
                and frame_count % VERIFY_INTERVAL_FRAMES == 0
                and verify_future is None
            ):
                verify_future = loop.run_in_executor(
                    VERIFY_EXECUTOR,
                    _post_verify_request,
                    sequence.tolist(),
                )

            # 5. 释放一次协程控制权，让 FastAPI/事件循环有机会处理网络发送和断开事件。
            await asyncio.sleep(0.01)

            # 6. 原有 4D YOLO 果蔬检测。
            detections, raw_img = detector.detect(color, depth)

            # 7. 缓存 raw_img 原始帧。必须 copy，避免后续绘制框或数组复用影响证据视频。
            frame_buffer.append(raw_img.copy())

            # 8. 如果 LSTM 判定当前窗口存在作弊，触发一次后台证据留存。
            # 注意：只提交线程池任务，主循环继续推送视频，绝不等待视频写盘或数据库写入。
            now = monotonic()
            can_create_alarm = (
                not current_is_secure
                and len(frame_buffer) > 0
                and (alarm_future is None or alarm_future.done())
                and now - last_alarm_at >= ALARM_COOLDOWN_SECONDS
            )
            if can_create_alarm:
                last_alarm_at = now
                transaction_id = _build_alarm_transaction_id(websocket)
                cached_frames = [frame.copy() for frame in frame_buffer]
                alarm_future = loop.run_in_executor(
                    ALARM_EXECUTOR,
                    _save_alarm_clip_and_insert_log,
                    cached_frames,
                    current_prediction,
                    current_lstm_score,
                    transaction_id,
                )

            annotated_img = _draw_detections(raw_img, detections)
            if hand_overlay_enabled:
                annotated_img = vision.draw_debug_overlay(annotated_img)

            # 9. WebSocket 前端展示使用 kg；LSTM 模型仍使用 raw_weight(g)。
            # max 用于抑制电子秤轻微漂移产生的负数。
            weight_kg = max(0.0, raw_weight / 1000.0)

            # 10. 编码当前帧为 base64 jpg，沿用原来的前端消费格式。
            _, buffer = cv2.imencode(".jpg", annotated_img)
            jpg_text = base64.b64encode(buffer).decode("utf-8")

            # 11. 构造防作弊信令。正常时只发送 status=normal；
            # 异常时额外发送 type，例如 swap 或 occlusion。
            security_signal = _build_security_signal(current_is_secure, current_prediction)

            message = {
                "image": jpg_text,
                "items": detections,
                "weight": weight_kg,
                "status": security_signal["status"],
                "lstm_score": round(current_lstm_score, 3),
                "occlusion_ratio": round(occlusion_ratio, 3),
                "occlusion_hold_seconds": round(occlusion_hold_seconds, 2),
                "hand_overlay_enabled": hand_overlay_enabled,
            }
            if security_signal["status"] == "alert":
                message["type"] = security_signal["type"]

            await websocket.send_json(message)

            frame_count += 1

    except Exception as exc:
        print(f"WebSocket disconnected or stopped: {exc}")
