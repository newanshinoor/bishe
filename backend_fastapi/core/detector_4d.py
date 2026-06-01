import torch
import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel

# 补丁：强制模型初始化为 4 通道
original_init = DetectionModel.__init__


def patched_init(self, cfg='yolov8n.yaml', ch=3, *args, **kwargs):
    original_init(self, cfg, 4, *args, **kwargs)


DetectionModel.__init__ = patched_init


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