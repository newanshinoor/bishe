import torch
import cv2
import numpy as np
import re
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel

# 补丁：强制模型初始化为 4 通道
original_init = DetectionModel.__init__


def patched_init(self, cfg='yolov8n.yaml', ch=3, *args, **kwargs):
    original_init(self, cfg, 4, *args, **kwargs)


DetectionModel.__init__ = patched_init


# 低置信度目标不参与“是否混放多种果蔬”的业务判断。
# YOLO 仍会保留原始检测框用于画面调试，计价只使用达到该阈值的有效框。
MULTI_ITEM_CONFIDENCE_THRESHOLD = 0.60


def normalize_product_category(label):
    """
    将 YOLO 类别名归一化为基础果蔬品类。

    模型类别通常包含新鲜度前缀，例如 freshApple、rottenApple、blemishApple。
    称重业务只关心是否为同一种果蔬，因此这些标签都应归一化为 apple。
    """
    normalized = re.sub(r"[^0-9a-z]+", "", str(label or "").lower())
    normalized = re.sub(r"(fresh|rotten|blemish)", "", normalized)
    return normalized or "unknown"


def analyze_detected_items(detections, confidence_threshold=MULTI_ITEM_CONFIDENCE_THRESHOLD):
    """
    分析有效检测框是否包含多种果蔬。

    返回结构会直接进入 WebSocket 消息：
    - normal: 0 或 1 个有效框；
    - same_category_multiple: 多个同品类框，按同一商品合并称重；
    - multi_item_error: 同时存在至少两种品类，停止计价。
    """
    effective_detections = [
        item.copy()
        for item in detections
        if float(item.get("conf", 0.0)) >= confidence_threshold
    ]
    categories = sorted({
        normalize_product_category(item.get("label"))
        for item in effective_detections
    })

    result = {
        "status": "normal",
        "error_code": None,
        "message": "",
        "confidence_threshold": confidence_threshold,
        "valid_detection_count": len(effective_detections),
        "detected_categories": categories,
        "effective_detections": effective_detections,
        "pricing_mode": "single_item",
    }

    if len(effective_detections) > 1 and len(categories) > 1:
        result.update({
            "status": "multi_item_error",
            "error_code": "MULTI_ITEM_ERROR",
            "message": "检测到多种果蔬，请一次仅放置一种商品称重",
            "pricing_mode": "blocked",
        })
    elif len(effective_detections) > 1:
        result.update({
            "status": "same_category_multiple",
            "message": "检测到多个同类目标，已按同一种商品合并称重",
            "pricing_mode": "merge_same_category",
        })

    return result


class FruitDetector4D:
    def __init__(self, model_path):
        self.model = YOLO(model_path)
        print(f"4D model loaded: {model_path}")

    def detect(self, color_img, depth_img):
        # 1. 统一尺寸为 640x640
        img_640 = cv2.resize(color_img, (640, 640))
        depth_640 = cv2.resize(depth_img, (640, 640))

        # 2. 构造 4 通道输入张量
        img_tensor = torch.from_numpy(img_640).permute(2, 0, 1).float() / 255.0
        depth_tensor = torch.from_numpy(depth_640).float() / 65535.0
        input_4d = torch.cat([img_tensor, depth_tensor.unsqueeze(0)], dim=0).unsqueeze(0)

        # 将张量移动到模型所在设备
        input_4d = input_4d.to(next(self.model.model.parameters()).device)

        # 3. 推理
        results = self.model.predict(source=input_4d, verbose=False)

        # 4. 提取检测结果（这里只提取，不画图，绘图留到外层篡改标签后再画）
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                label = self.model.names[int(box.cls[0])]

                detections.append({
                    "label": label,
                    "conf": conf,
                    "bbox": [x1, y1, x2, y2]
                })

        return detections, img_640
