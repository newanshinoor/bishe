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
from sqlalchemy import text

# 兼容不同启动目录：
# - 从 backend_fastapi 启动时，需要项目根目录才能导入 model_training；
# - 从项目根目录启动时，需要 backend_fastapi 目录才能导入 core。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
for path in (BASE_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.append(path)

from core.camera_driver import AstraCamera
from core.depth_validator import DepthValidator
from core.detection_analysis import analyze_detected_items
from core.detector_rgb import RGBFruitDetector
from core.fruit_detection_stabilizer import FruitDetectionStabilizer
from core.alarm_log import AlarmLog
from core.database import SessionLocal
from core.order_video import cache_order_video_frame
from core.realtime_anti_cheat import RealtimeOcclusionGuard, RealtimeWeightGuard
from core.scale_driver import RealTimeScale
from core.system_config import get_runtime_config
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
DETECTOR_MODE = os.getenv("DETECTOR_MODE", "rgb_depth_aux").strip().lower()

try:
    STREAM_JPEG_QUALITY = max(1, min(100, int(os.getenv("STREAM_JPEG_QUALITY", "90"))))
except (TypeError, ValueError):
    STREAM_JPEG_QUALITY = 90

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
# 遮挡比例仍按论文使用 0.8；持续时间由 system_config 动态配置。
OCCLUSION_RATIO_THRESHOLD = 0.8
# 高遮挡持续一小段时间后，先进入候选态。候选态会压住 LSTM 对遮挡动作的
# swap/lift 误分类；持续时间达到管理员配置阈值后再升级为 occlusion 告警。
OCCLUSION_CANDIDATE_SECONDS = 0.8
# 重量保护层检测到短促动作后锁存一小段时间，避免随后返回的异步 LSTM
# 普通结果立即覆盖告警，导致前端只能看到一帧。
WEIGHT_GUARD_ALERT_SECONDS = 2.0

# Suppress swap/lift when the scale is effectively empty. A hand-only frame can
# look like a swap sequence to the LSTM, but transaction anti-cheat requires a
# real weighted item on the scale.
MIN_OBJECT_WEIGHT_GRAMS = float(os.getenv("MIN_OBJECT_WEIGHT_GRAMS", "30"))
WEIGHT_REQUIRED_LSTM_PREDICTIONS = {"swap", "lift"}

# HTTP 请求必须放到线程池中执行，避免 requests.post 阻塞事件循环，
# 从而保证 WebSocket 视频流和重量数据持续推送。
VERIFY_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="anti-cheat")

# 视频写盘与数据库写入使用独立线程池，和 LSTM HTTP 请求隔离。
# max_workers=1 可以避免多个 VideoWriter 同时抢占磁盘 I/O。
ALARM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alarm-evidence")


# =========================
# 全局硬件与算法模块初始化
# =========================

# 摄像头、RGB YOLO 检测器、Depth 校验器、电子秤全局初始化。
camera = AstraCamera()
detector = RGBFruitDetector()
depth_validator = DepthValidator()
scale = RealTimeScale()

# LSTM 多模态防作弊模块：
# vision 负责从视频帧提取手部/遮挡特征；
# WebSocket 会话会各自创建 DataAligner，避免上一次作弊窗口污染下一次识别。
vision = HandVisionProcessor(roi_box=[0.2, 0.4, 0.8, 1.0])
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


def _has_weighted_item(raw_weight: float) -> bool:
    return max(0.0, float(raw_weight)) >= MIN_OBJECT_WEIGHT_GRAMS


def _should_suppress_empty_scale_prediction(prediction: str, raw_weight: float) -> bool:
    return (
        prediction in WEIGHT_REQUIRED_LSTM_PREDICTIONS
        and not _has_weighted_item(raw_weight)
    )


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
    """绘制模型原始检测框，不修改模型输出标签。"""
    annotated_img = raw_img.copy()

    for item in detections:
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


TERMINAL_PRICE_FALLBACK = {
    "苹果": 4.5,
    "西红柿": 3.2,
    "芒果": 8.5,
    "橙子": 5.0,
    "香蕉": 3.5,
    "黄瓜": 2.8,
    "草莓": 12.0,
    "葡萄": 10.0,
    "土豆": 2.0,
    "西瓜": 3.0,
}


def _resolve_unit_price(display_name: str, freshness: str) -> float:
    db = SessionLocal()
    try:
        unit_price = db.execute(
            text("SELECT price FROM fruit_inventory WHERE item_name = :item_name LIMIT 1"),
            {"item_name": display_name},
        ).scalar()
        if unit_price is None:
            unit_price = TERMINAL_PRICE_FALLBACK.get(display_name)
        if unit_price is None:
            return 0.0

        unit_price = float(unit_price)
        if freshness == "腐烂":
            return 0.0
        if freshness == "瑕疵":
            return round(unit_price * 0.5, 2)
        return round(unit_price, 2)
    except Exception:
        return round(float(TERMINAL_PRICE_FALLBACK.get(display_name, 0.0)), 2)
    finally:
        db.close()


def _attach_pricing(stable_result: Dict[str, Any], weight_kg: float) -> Dict[str, Any]:
    display_name = str(stable_result.get("display_name") or stable_result.get("label") or "未识别商品")
    freshness = str(stable_result.get("freshness") or "普通")
    unit_price = _resolve_unit_price(display_name, freshness)
    return {
        **stable_result,
        "display_name": display_name,
        "freshness": freshness,
        "unit_price": unit_price,
        "total_price": round(unit_price * max(0.0, float(weight_kg)), 2),
    }


@router.websocket("/ws")
async def video_feed(websocket: WebSocket):
    """
    WebSocket 实时视频流主循环。

    每一轮循环完成以下工作：
    1. 采集 RGB/Depth 帧；
    2. 非阻塞提取手部视觉特征和电子秤重量特征；
    3. 将 4 维视觉特征 + 2 维重量特征写入 DataAligner；
    4. 使用 RGB YOLO 识别果蔬，并用 Depth 做辅助校验；
    5. 满 60 帧后，每 10 帧异步请求一次 /api/transaction/verify；
    6. 将视频、检测结果、重量和防作弊状态一起推送给前端。
    """
    await websocket.accept()

    # 每次重新点击“开始识别”都会建立新的 WebSocket。
    # 对齐窗口必须属于当前连接，不能复用上一次作弊发生时残留的 60 帧。
    session_aligner = DataAligner(window_size=ALIGN_WINDOW_SIZE)
    fruit_stabilizer = FruitDetectionStabilizer()
    weight_guard = RealtimeWeightGuard()
    occlusion_guard = RealtimeOcclusionGuard(
        ratio_threshold=OCCLUSION_RATIO_THRESHOLD,
        candidate_hold_seconds=OCCLUSION_CANDIDATE_SECONDS,
    )
    frame_count = 0
    verify_future: Optional[asyncio.Future] = None
    alarm_future: Optional[asyncio.Future] = None

    # 持续缓存最近 6 秒 raw_img 原始帧，供作弊瞬间生成证据视频。
    frame_buffer: Deque = deque(maxlen=FRAME_BUFFER_MAXLEN)

    # 默认状态为正常。只有后台校验接口明确返回 is_secure=False 时才报警。
    current_prediction = "normal"
    current_is_secure = True
    current_lstm_score = 0.0
    current_detection_source = "normal"
    current_detection_reason = ""
    active_weight_violation = None
    weight_guard_alert_until = 0.0
    last_alarm_at = 0.0
    occlusion_hold_seconds = 0.0

    try:
        loop = asyncio.get_running_loop()

        while True:
            # 配置服务优先返回内存快照，后台保存后立即更新，无需重启服务。
            runtime_config = get_runtime_config()

            # 1. 采集 Astra 相机的彩色帧和深度帧。
            color, depth = camera.get_frames()
            display_frame = color.copy()
            infer_frame = display_frame.copy()

            # 2. LSTM 多模态防作弊特征采集。
            # vision.extract_features 只做手部关键点/ROI 特征提取；
            # scale.get_features 返回 [当前重量, 重量变化量]。
            # 二者都在当前帧周期内完成，并立即送入 aligner 形成同步滑窗。
            vision_features = vision.extract_features(display_frame)
            raw_weight, weight_diff = scale.get_features()
            if camera.is_mock and not scale.connected and not getattr(scale, "is_mock", False):
                raw_weight = float(os.getenv("MOCK_WEIGHT_GRAMS", "500"))
                weight_diff = 0.0
            scale_has_item = _has_weighted_item(raw_weight)
            session_aligner.update(vision_features, [raw_weight, weight_diff])

            # 论文中的部分遮挡特征为 ROI 内关键点数量 / 21。
            # 仅当该比例持续超过阈值 5 秒，才允许 occlusion 告警通过。
            occlusion_ratio = float(vision_features[3])
            now = monotonic()
            occlusion_violation = occlusion_guard.update(
                now=now,
                occlusion_ratio=occlusion_ratio,
                weight=raw_weight,
                weight_diff=weight_diff,
                alert_hold_seconds=runtime_config.occlusion_duration_threshold,
            )
            occlusion_hold_seconds = occlusion_guard.hold_seconds

            # 串口读取频率和视频帧率不同。逐条消费帧间重量跳变，避免快速拿走再放回
            # 在净变化量中相互抵消。没有新跳变时仍推进一次，以便托举持续计时。
            weight_events = scale.consume_weight_events()
            if not weight_events:
                weight_events = [(now, raw_weight, 0.0)]

            guard_violation = None
            for event_at, event_weight, event_diff in weight_events:
                violation = weight_guard.update(
                    now=event_at,
                    weight=event_weight,
                    weight_diff=event_diff,
                    vision_features=vision_features,
                )
                if violation is not None:
                    guard_violation = violation

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
                    current_detection_source = "lstm"
                    current_detection_reason = ""

                    # 低置信度输出不拦截，阈值可由管理员后台实时微调。
                    if current_lstm_score < runtime_config.anti_cheat_threshold:
                        current_is_secure = True

                    if _should_suppress_empty_scale_prediction(current_prediction, raw_weight):
                        suppressed_prediction = current_prediction
                        current_prediction = "normal"
                        current_is_secure = True
                        current_lstm_score = 0.0
                        current_detection_source = "lstm_suppressed"
                        current_detection_reason = (
                            f"Scale weight {raw_weight:.1f}g is below "
                            f"{MIN_OBJECT_WEIGHT_GRAMS:.1f}g; suppressed "
                            f"{suppressed_prediction}."
                        )

                    # 部分遮挡还要满足 ROI 占比连续保持超过管理员配置的持续时间。
                    if (
                        current_prediction == "occlusion"
                        and not occlusion_guard.is_alert_ready(
                            runtime_config.occlusion_duration_threshold
                        )
                    ):
                        current_is_secure = True

            # LSTM 是主判定器；重量轨迹保护层补强现场演示中非常短促的替换动作，
            # 以及低重量商品的持续托举动作。保护层同样服从管理员配置的告警阈值。
            if guard_violation is not None:
                active_weight_violation = guard_violation
                weight_guard_alert_until = now + WEIGHT_GUARD_ALERT_SECONDS

            if now >= weight_guard_alert_until:
                active_weight_violation = None

            if (
                active_weight_violation is not None
                and active_weight_violation.score >= runtime_config.anti_cheat_threshold
            ):
                current_prediction = active_weight_violation.prediction
                current_is_secure = False
                current_lstm_score = active_weight_violation.score
                current_detection_source = "weight_guard"
                current_detection_reason = active_weight_violation.reason

            if _should_suppress_empty_scale_prediction(current_prediction, raw_weight):
                suppressed_prediction = current_prediction
                current_prediction = "normal"
                current_is_secure = True
                current_lstm_score = 0.0
                current_detection_source = "empty_scale_guard"
                current_detection_reason = (
                    f"Scale weight {raw_weight:.1f}g is below "
                    f"{MIN_OBJECT_WEIGHT_GRAMS:.1f}g; suppressed "
                    f"{suppressed_prediction}."
                )

            # 遮挡特征是连续高 ROI 占比。先抑制候选期内的 swap/lift 误分类，
            # 达到配置时长后再以最高优先级明确输出 occlusion。
            if occlusion_violation is not None:
                current_prediction = occlusion_violation.prediction
                current_is_secure = False
                current_lstm_score = max(current_lstm_score, occlusion_violation.score)
                current_detection_source = "occlusion_guard"
                current_detection_reason = occlusion_violation.reason
            elif (
                occlusion_guard.is_candidate
                and current_prediction in {"swap", "lift"}
            ):
                current_prediction = "occlusion_pending"
                current_is_secure = True
                current_lstm_score = 0.0
                current_detection_source = "occlusion_guard"
                current_detection_reason = "ROI 内持续高遮挡，等待达到遮挡告警时长"

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
            sequence = session_aligner.get_sequence()
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

            # 6. RGB YOLO 分类 + Depth 辅助校验。
            detections, _ = detector.detect(infer_frame)
            item_analysis = analyze_detected_items(
                detections,
                confidence_threshold=runtime_config.min_confidence_threshold,
            )

            validated_detections = []
            depth_checks = []
            frame_status = item_analysis["status"]
            frame_message = item_analysis["message"]

            if frame_status != "multi_item_error":
                for detection in item_analysis["effective_detections"]:
                    depth_check = depth_validator.validate_detection(
                        detection,
                        depth,
                        rgb_shape=infer_frame.shape[:2],
                    )
                    enriched = {**detection, "depth_check": depth_check}
                    depth_checks.append(depth_check)
                    if depth_check.get("valid"):
                        validated_detections.append(enriched)
                        continue

                    reason = str(depth_check.get("reason") or "")
                    if reason in {
                        "target_not_on_scale",
                        "occlusion_detected",
                        "invalid_depth",
                        "depth_out_of_range",
                    }:
                        frame_status = reason
                        frame_message = {
                            "target_not_on_scale": "请将商品放置到秤面中央",
                            "occlusion_detected": "检测到遮挡，请移开手部或遮挡物",
                            "invalid_depth": "深度数据不可用，请检查深度相机",
                            "depth_out_of_range": "商品距离超出有效深度范围",
                        }.get(reason, frame_message)
                        break

            if frame_status == "normal" and not validated_detections:
                if detections:
                    frame_status = "low_confidence"
                    frame_message = "识别置信度较低，请重新摆放商品"
                else:
                    frame_status = "no_object"
                    frame_message = "未检测到商品"

            recognition = fruit_stabilizer.update(
                validated_detections,
                raw_weight,
                now=monotonic(),
                frame_status=frame_status,
                frame_message=frame_message,
            )

            # 多种果蔬混放时停止计价：前端只收到空 items，不会继续按最高置信度商品计价。
            # 多个同类框则继续使用有效框，由前端按最高置信度框确定商品名称，
            # 重量仍来自电子秤总重量，相当于按同一种商品合并称重。
            pricing_items = item_analysis["effective_detections"]
            pricing_items = []

            # 7. 缓存浏览器显示用原始比例帧。必须 copy，避免后续绘制框或数组复用影响证据视频。
            frame_buffer.append(display_frame.copy())
            cache_order_video_frame(display_frame)

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

            annotated_img = _draw_detections(display_frame, detections)
            if hand_overlay_enabled:
                annotated_img = vision.draw_debug_overlay(annotated_img)

            # 9. WebSocket 前端展示使用 kg；LSTM 模型仍使用 raw_weight(g)。
            # max 用于抑制电子秤轻微漂移产生的负数。
            weight_kg = max(0.0, raw_weight / 1000.0)
            stable_result = recognition["stable_result"]
            if stable_result is not None:
                stable_result = _attach_pricing({
                    **stable_result,
                    "weight": weight_kg,
                    "weight_kg": weight_kg,
                }, weight_kg)
                pricing_items = [stable_result]

            # 10. 编码当前帧为 base64 jpg，沿用原来的前端消费格式。
            _, buffer = cv2.imencode(
                ".jpg",
                annotated_img,
                [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY],
            )
            jpg_text = base64.b64encode(buffer).decode("utf-8")

            # 11. 构造防作弊信令。正常时只发送 status=normal；
            # 异常时额外发送 type，例如 swap 或 occlusion。
            security_signal = _build_security_signal(current_is_secure, current_prediction)

            message = {
                "image": jpg_text,
                "image_width": int(annotated_img.shape[1]),
                "image_height": int(annotated_img.shape[0]),
                "items": pricing_items,
                "stable_result": stable_result,
                "raw_detections": detections,
                "depth_checks": depth_checks,
                "weight": weight_kg,
                "scale_has_item": scale_has_item,
                "min_object_weight_grams": MIN_OBJECT_WEIGHT_GRAMS,
                "status": security_signal["status"],
                "recognition_status": recognition["status"],
                "recognition_message": recognition["message"],
                "weight_stable": recognition["weight_stable"],
                "recognition_vote_ratio": recognition["vote_ratio"],
                "recognition_average_confidence": recognition["average_confidence"],
                "recognition_sample_count": recognition["sample_count"],
                "inference_mode": detector.last_inference_mode,
                "detector_mode": DETECTOR_MODE,
                "camera_mode": camera.mode,
                "item_status": frame_status,
                "error_code": item_analysis["error_code"] if frame_status == item_analysis["status"] else frame_status.upper(),
                "message": frame_message or recognition["message"],
                "pricing_mode": item_analysis["pricing_mode"],
                "valid_detection_count": len(validated_detections),
                "detected_categories": item_analysis["detected_categories"],
                "lstm_score": round(current_lstm_score, 3),
                "occlusion_ratio": round(occlusion_ratio, 3),
                "occlusion_hold_seconds": round(occlusion_hold_seconds, 2),
                "hand_overlay_enabled": hand_overlay_enabled,
                "anti_cheat_threshold": runtime_config.anti_cheat_threshold,
                "occlusion_duration_threshold": runtime_config.occlusion_duration_threshold,
                "min_confidence_threshold": runtime_config.min_confidence_threshold,
                "detection_source": current_detection_source,
                "detection_reason": current_detection_reason,
            }
            if security_signal["status"] == "alert":
                message["type"] = security_signal["type"]
            elif frame_status != "normal":
                message["status"] = frame_status

            await websocket.send_json(message)

            frame_count += 1

    except Exception as exc:
        print(f"WebSocket disconnected or stopped: {exc}")
    finally:
        # 显式释放当前连接的历史帧，重新开始识别时必须重新采样完整窗口。
        session_aligner.reset()
        fruit_stabilizer.reset()
        weight_guard.reset()
        occlusion_guard.reset()
