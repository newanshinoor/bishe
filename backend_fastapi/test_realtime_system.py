import cv2
import time
import requests
import numpy as np

# 导入你之前写好的模块 (注意根据你的实际路径调整 import)
from backend_fastapi.core.scale_driver import RealTimeScale
from model_training.LSTM.vision_processor import HandVisionProcessor
from model_training.LSTM.preprocess import DataAligner

# 配置你的接口地址
API_URL = "http://localhost:8000/api/transaction/verify"


def run_system_test():
    print("🚀 正在启动交易防作弊多模态融合系统...")

    # 1. 初始化各模块
    # 注意把 COM5 换成你 Arduino 实际的端口
    scale = RealTimeScale(port='COM5', baud=115200)
    vision = HandVisionProcessor(roi_box=[0.2, 0.4, 0.8, 1.0])  # 假设秤面在画面中下方
    aligner = DataAligner(window_size=60)

    # 2. 打开摄像头 (0代表默认笔记本摄像头，如果你外接了摄像头可能是1)
    cap = cv2.VideoCapture(0)

    # 状态变量
    current_status = "Waiting..."
    is_secure = True
    frame_count = 0

    print("✅ 系统初始化完成，按 'q' 键退出。")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)  # 镜像翻转，符合直觉

            # --- A. 提取视觉特征 ---
            vis_features = vision.extract_features(frame)

            # --- B. 提取重量特征 ---
            weight, weight_diff = scale.get_features()

            # --- C. 数据融合与对齐 ---
            aligner.update(vis_features, [weight, weight_diff])

            # --- D. 触发模型判定 (每满 60 帧，且每隔 10 帧请求一次后端) ---
            sequence = aligner.get_sequence()
            if sequence is not None and frame_count % 10 == 0:
                try:
                    payload = {"sequence": sequence.tolist()}
                    # 设定短超时避免画面卡顿
                    res = requests.post(API_URL, json=payload, timeout=0.5).json()
                    current_status = res.get("prediction", "unknown").upper()
                    is_secure = res.get("is_secure", True)
                except requests.exceptions.RequestException:
                    current_status = "API Offline"

            # --- E. 画面可视化 (非常适合答辩演示) ---
            # 1. 画出秤面 ROI 区域
            h, w, _ = frame.shape
            roi = vision.roi
            cv2.rectangle(frame, (int(roi[0] * w), int(roi[1] * h)), (int(roi[2] * w), int(roi[3] * h)), (255, 255, 0),
                          2)

            # 2. 在左上角显示当前数据和判定结果
            color = (0, 255, 0) if is_secure else (0, 0, 255)  # 正常绿色，异常红色
            cv2.putText(frame, f"Weight: {weight:.1f} g", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, f"Diff: {weight_diff:.1f} g", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255),
                        2)
            cv2.putText(frame, f"Occ Ratio: {vis_features[3]:.2f}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (255, 255, 255), 2)
            cv2.putText(frame, f"Status: {current_status}", (20, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)

            cv2.imshow("Smart Retail Anti-Cheat System", frame)

            frame_count += 1

            # 维持约 10Hz 左右的循环频率 (100ms)
            if cv2.waitKey(80) & 0xFF == ord('q'):
                break

    finally:
        # 清理资源
        cap.release()
        cv2.destroyAllWindows()
        scale.close()


if __name__ == "__main__":
    run_system_test()