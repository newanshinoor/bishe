from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "backend_fastapi"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from core.rgbd_preprocessing import prepare_rgbd_training_array


original_init = DetectionModel.__init__


def patched_init(self, cfg="yolov8n.yaml", ch=3, *args, **kwargs):
    original_init(self, cfg, 4, *args, **kwargs)


DetectionModel.__init__ = patched_init


def load_rgbd_array(img_path: str, npy_path: str) -> np.ndarray:
    color_bgr = cv2.imread(img_path)
    if color_bgr is None:
        raise ValueError(f"Unable to read RGB image: {img_path}")

    saved_array = np.load(npy_path)
    if saved_array.ndim == 3 and saved_array.shape[2] >= 4:
        rgbd_array = saved_array[:, :, :4]
        if rgbd_array.shape[:2] != (640, 640):
            rgbd_array = cv2.resize(rgbd_array, (640, 640), interpolation=cv2.INTER_NEAREST)
        return rgbd_array.astype(np.uint8)

    return prepare_rgbd_training_array(color_bgr, saved_array)


def test_single_image(model_path: str, img_path: str, npy_path: str) -> None:
    if not os.path.exists(npy_path):
        print(f"Missing RGB-D file: {npy_path}")
        return

    model = YOLO(model_path)
    rgbd_array = load_rgbd_array(img_path, npy_path)
    input_4d = torch.from_numpy(rgbd_array).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    input_4d = input_4d.to(next(model.model.parameters()).device)

    for result in model.predict(source=input_4d, save=True):
        print(f"{os.path.basename(img_path)} detections:")
        for box in result.boxes:
            name = model.names[int(box.cls[0])]
            confidence = float(box.conf[0])
            print(f"  - {name}: {confidence:.2f}")


if __name__ == "__main__":
    model_path = str(PROJECT_ROOT / "model_training" / "yolo" / "best.pt")
    samples = [
        {
            "img": PROJECT_ROOT / "model_training" / "yolo" / "input_rgb" / "test" / "images" / "freshApple-460-_png.rf.dd16aac1f1b21863eb44be2061a4f595.jpg",
            "npy": PROJECT_ROOT / "model_training" / "yolo" / "dataset_4d" / "images" / "test" / "freshApple-460-_png.rf.dd16aac1f1b21863eb44be2061a4f595.npy",
        },
    ]

    for sample in samples:
        if sample["img"].exists():
            test_single_image(model_path, str(sample["img"]), str(sample["npy"]))
        else:
            print(f"Skip missing image: {sample['img']}")
