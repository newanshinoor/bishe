from __future__ import annotations

import os
from typing import Optional

import torch
from ultralytics import YOLO

from core.detection_analysis import (
    MULTI_ITEM_CONFIDENCE_THRESHOLD,
    analyze_detected_items,
    normalize_product_category,
)
from core.rgbd_preprocessing import normalize_depth_mm, resize_bgr_to_rgb


class FruitDetector4D:
    def __init__(self, model_path: str, rgb_only_model_path: Optional[str] = None):
        self.model = YOLO(model_path)
        self.rgb_only_model = None
        self.last_inference_mode = "rgbd"

        fallback_path = rgb_only_model_path or os.getenv("RGB_ONLY_MODEL_PATH")
        if fallback_path:
            self.rgb_only_model = YOLO(fallback_path)
            print(f"RGB-only fallback model loaded: {fallback_path}")

        print(f"4D model loaded: {model_path}")

    def detect(self, color_img, depth_img):
        display_bgr, rgb_640 = resize_bgr_to_rgb(color_img)
        rgb_tensor = torch.from_numpy(rgb_640).permute(2, 0, 1).float() / 255.0
        normalized_depth = normalize_depth_mm(depth_img)

        if normalized_depth is None and self.rgb_only_model is not None:
            self.last_inference_mode = "rgb_only_fallback"
            input_tensor = rgb_tensor.unsqueeze(0)
            model = self.rgb_only_model
        else:
            self.last_inference_mode = "rgbd" if normalized_depth is not None else "rgbd_zero_depth"
            if normalized_depth is None:
                normalized_depth = torch.zeros((640, 640), dtype=torch.float32).numpy()
            depth_tensor = torch.from_numpy(normalized_depth).float()
            input_tensor = torch.cat([rgb_tensor, depth_tensor.unsqueeze(0)], dim=0).unsqueeze(0)
            model = self.model

        input_tensor = input_tensor.to(next(model.model.parameters()).device)
        results = model.predict(source=input_tensor, verbose=False)

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append({
                    "label": model.names[int(box.cls[0])],
                    "conf": float(box.conf[0]),
                    "bbox": [x1, y1, x2, y2],
                })

        return detections, display_bgr
