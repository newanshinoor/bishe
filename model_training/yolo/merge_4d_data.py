from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend_fastapi"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from core.rgbd_preprocessing import prepare_rgbd_training_array


SPLIT = os.getenv("DATASET_SPLIT", "train").strip().lower()
RGB_DIR = PROJECT_ROOT / "model_training" / "yolo" / "input_rgb" / SPLIT / "images"
LABEL_DIR = PROJECT_ROOT / "model_training" / "yolo" / "input_rgb" / SPLIT / "labels"
DEPTH_DIR = PROJECT_ROOT / "model_training" / "yolo" / "output_depth" / f"{SPLIT}_depth"
OUTPUT_IMAGE_DIR = PROJECT_ROOT / "model_training" / "yolo" / "dataset_4d" / "images" / SPLIT
OUTPUT_LABEL_DIR = PROJECT_ROOT / "model_training" / "yolo" / "dataset_4d" / "labels" / SPLIT
OUTPUT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_LABEL_DIR.mkdir(parents=True, exist_ok=True)


def read_image(path: Path, flags: int):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), flags)


def find_rgb_path(base_name: str):
    for extension in (".jpg", ".JPG", ".png", ".PNG", ".jpeg", ".webp"):
        candidate = RGB_DIR / f"{base_name}{extension}"
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    depth_files = [
        path
        for path in DEPTH_DIR.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]

    success_count = 0
    for depth_path in depth_files:
        rgb_path = find_rgb_path(depth_path.stem)
        if rgb_path is None:
            print(f"Skip: no matching RGB image for {depth_path.name}")
            continue

        color_bgr = read_image(rgb_path, cv2.IMREAD_COLOR)
        depth_img = read_image(depth_path, cv2.IMREAD_UNCHANGED)
        if color_bgr is None or depth_img is None:
            print(f"Skip: unable to read RGB-D pair {depth_path.stem}")
            continue

        rgbd_array = prepare_rgbd_training_array(color_bgr, depth_img)
        np.save(OUTPUT_IMAGE_DIR / f"{depth_path.stem}.npy", rgbd_array)

        label_path = LABEL_DIR / f"{depth_path.stem}.txt"
        if label_path.exists():
            shutil.copyfile(label_path, OUTPUT_LABEL_DIR / label_path.name)
        else:
            print(f"Warning: no matching YOLO label for {depth_path.stem}")
        success_count += 1

    print(f"RGB-D merge complete: {success_count} {SPLIT} samples saved to {OUTPUT_IMAGE_DIR}")


if __name__ == "__main__":
    main()
