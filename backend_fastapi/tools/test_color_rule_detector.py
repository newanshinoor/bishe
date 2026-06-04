from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def parse_roi(roi_text: str) -> list[float]:
    try:
        values = [float(x.strip()) for x in roi_text.split(",")]
        if len(values) != 4:
            raise ValueError
        x1, y1, x2, y2 = values
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError
        return values
    except Exception:
        raise ValueError("ROI格式错误，应为 x1,y1,x2,y2，例如 0.10,0.20,0.90,0.95")


def depth_to_vis(depth: Optional[np.ndarray], min_mm: int = 300, max_mm: int = 2000) -> np.ndarray:
    if depth is None:
        return np.zeros((240, 320, 3), dtype=np.uint8)

    depth_clip = depth.copy()
    depth_clip[depth_clip == 0] = min_mm
    depth_clip = np.clip(depth_clip, min_mm, max_mm)
    norm = ((depth_clip - min_mm) / max(1, max_mm - min_mm) * 255).astype(np.uint8)
    return cv2.applyColorMap(norm, cv2.COLORMAP_JET)


class ColorRuleDetector:
    def __init__(
        self,
        roi: list[float],
        min_area_ratio: float,
        max_object_depth_mm: int,
        min_valid_depth_mm: int,
        max_valid_depth_mm: int,
        min_depth_valid_ratio: float,
    ):
        self.roi = roi
        self.min_area_ratio = min_area_ratio
        self.max_object_depth_mm = max_object_depth_mm
        self.min_valid_depth_mm = min_valid_depth_mm
        self.max_valid_depth_mm = max_valid_depth_mm
        self.min_depth_valid_ratio = min_depth_valid_ratio

        # OpenCV HSV: H范围 0~179，S/V范围 0~255
        # 苹果：粉红/粉红偏红；香蕉：黄色；黄瓜：青绿色
        self.rules = [
            {
                "label": "apple",
                "display_name": "苹果",
                "box_color": (180, 105, 255),  # BGR 粉色
                "conf": 0.92,
                "ranges": [
                    # 粉红偏红：低H红色段，降低S阈值以适配粉红苹果
                    ((0, 25, 70), (15, 230, 255)),
                    # 粉红/洋红段
                    ((155, 20, 70), (179, 230, 255)),
                ],
            },
            {
                "label": "banana",
                "display_name": "香蕉",
                "box_color": (0, 255, 255),
                "conf": 0.90,
                "ranges": [
                    ((18, 45, 45), (38, 255, 255)),
                ],
            },
            {
                "label": "cucumber",
                "display_name": "黄瓜",
                "box_color": (0, 255, 0),
                "conf": 0.90,
                "ranges": [
                    ((38, 35, 35), (95, 255, 255)),
                ],
            },
        ]

    def get_roi_box(self, frame: np.ndarray) -> Tuple[int, int, int, int]:
        h, w = frame.shape[:2]
        x1 = int(self.roi[0] * w)
        y1 = int(self.roi[1] * h)
        x2 = int(self.roi[2] * w)
        y2 = int(self.roi[3] * h)
        return x1, y1, x2, y2

    def build_mask(self, hsv_roi: np.ndarray, ranges) -> np.ndarray:
        mask_total = np.zeros(hsv_roi.shape[:2], dtype=np.uint8)

        for lower, upper in ranges:
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            mask = cv2.inRange(hsv_roi, lower_np, upper_np)
            mask_total = cv2.bitwise_or(mask_total, mask)

        kernel = np.ones((5, 5), np.uint8)
        mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_CLOSE, kernel, iterations=2)

        return mask_total

    def find_bbox(
        self,
        mask: np.ndarray,
        offset_x: int,
        offset_y: int,
        full_area: int,
    ):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, 0.0, 0.0

        best = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(best))
        min_area = full_area * self.min_area_ratio

        if area < min_area:
            return None, area, 0.0

        x, y, w, h = cv2.boundingRect(best)

        if w <= 8 or h <= 8:
            return None, area, 0.0

        x1 = x + offset_x
        y1 = y + offset_y
        x2 = x1 + w
        y2 = y1 + h

        box_area = max(1, w * h)
        fill_ratio = min(1.0, area / box_area)

        return [int(x1), int(y1), int(x2), int(y2)], area, fill_ratio

    def get_bbox_depth(self, depth: Optional[np.ndarray], bbox: list[int]) -> dict:
        if depth is None:
            return {
                "depth_available": False,
                "median_depth_mm": None,
                "valid_ratio": 0.0,
                "depth_ok": True,
                "reason": "no_depth_source",
            }

        h, w = depth.shape[:2]
        x1, y1, x2, y2 = bbox

        x1 = max(0, min(w - 1, int(x1)))
        x2 = max(0, min(w, int(x2)))
        y1 = max(0, min(h - 1, int(y1)))
        y2 = max(0, min(h, int(y2)))

        if x2 <= x1 or y2 <= y1:
            return {
                "depth_available": True,
                "median_depth_mm": None,
                "valid_ratio": 0.0,
                "depth_ok": False,
                "reason": "invalid_bbox",
            }

        roi_depth = depth[y1:y2, x1:x2]
        valid = roi_depth[
            (roi_depth >= self.min_valid_depth_mm)
            & (roi_depth <= self.max_valid_depth_mm)
        ]

        valid_ratio = float(valid.size / max(1, roi_depth.size))

        if valid.size == 0 or valid_ratio < self.min_depth_valid_ratio:
            return {
                "depth_available": True,
                "median_depth_mm": None,
                "valid_ratio": round(valid_ratio, 4),
                "depth_ok": False,
                "reason": "invalid_depth",
            }

        median_depth = int(np.median(valid))

        if median_depth > self.max_object_depth_mm:
            return {
                "depth_available": True,
                "median_depth_mm": median_depth,
                "valid_ratio": round(valid_ratio, 4),
                "depth_ok": False,
                "reason": f"too_far_over_{self.max_object_depth_mm}mm",
            }

        return {
            "depth_available": True,
            "median_depth_mm": median_depth,
            "valid_ratio": round(valid_ratio, 4),
            "depth_ok": True,
            "reason": "ok",
        }

    def detect(
        self,
        frame_bgr: np.ndarray,
        depth: Optional[np.ndarray],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, np.ndarray]]:
        h, w = frame_bgr.shape[:2]
        full_area = h * w

        if depth is not None and depth.shape[:2] != frame_bgr.shape[:2]:
            depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_NEAREST)

        rx1, ry1, rx2, ry2 = self.get_roi_box(frame_bgr)
        roi_bgr = frame_bgr[ry1:ry2, rx1:rx2]

        blur = cv2.GaussianBlur(roi_bgr, (5, 5), 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)

        visible_detections = []
        all_candidates = []
        masks = {}

        for rule in self.rules:
            mask = self.build_mask(hsv, rule["ranges"])
            masks[rule["label"]] = mask

            bbox, area, fill_ratio = self.find_bbox(mask, rx1, ry1, full_area)

            if bbox is None:
                continue

            conf = max(0.55, min(float(rule["conf"]), 0.65 + 0.35 * fill_ratio))
            depth_info = self.get_bbox_depth(depth, bbox)

            candidate = {
                "label": rule["label"],
                "display_name": rule["display_name"],
                "bbox": bbox,
                "area": area,
                "fill_ratio": fill_ratio,
                "conf": round(conf, 3),
                "box_color": rule["box_color"],
                "depth": depth_info,
            }
            all_candidates.append(candidate)

            # 核心规则：深度超过1m或深度无效，不显示识别结果
            if depth_info["depth_ok"]:
                visible_detections.append(candidate)

        visible_detections.sort(key=lambda d: d["area"], reverse=True)
        all_candidates.sort(key=lambda d: d["area"], reverse=True)

        return visible_detections, all_candidates, masks

    def draw(
        self,
        frame_bgr: np.ndarray,
        visible_detections: List[Dict[str, Any]],
        all_candidates: List[Dict[str, Any]],
    ) -> np.ndarray:
        out = frame_bgr.copy()

        rx1, ry1, rx2, ry2 = self.get_roi_box(out)
        cv2.rectangle(out, (rx1, ry1), (rx2, ry2), (255, 255, 255), 2)
        cv2.putText(
            out,
            "Color ROI",
            (rx1, max(20, ry1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        if visible_detections:
            # 测试阶段显示所有深度合格检测框；正式接入时一般取最大框
            for det in visible_detections:
                x1, y1, x2, y2 = det["bbox"]
                color = det["box_color"]
                depth_info = det["depth"]
                median_depth = depth_info["median_depth_mm"]

                label = f"{det['label']} {det['conf']:.2f}"
                if median_depth is not None:
                    label += f" {median_depth}mm"

                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    out,
                    label,
                    (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    color,
                    2,
                )
        else:
            text = "No valid target within 1m"
            if all_candidates:
                best = all_candidates[0]
                depth_info = best["depth"]
                if depth_info["median_depth_mm"] is not None:
                    text = f"Hidden: {best['label']} depth={depth_info['median_depth_mm']}mm > limit"
                else:
                    text = f"Hidden: {best['label']} depth invalid"

            cv2.putText(
                out,
                text,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

        return out


def make_mask_panel(masks: Dict[str, np.ndarray], width: int = 320, height: int = 240) -> np.ndarray:
    panels = []

    for name in ["apple", "banana", "cucumber"]:
        mask = masks.get(name)
        if mask is None:
            mask = np.zeros((height, width), dtype=np.uint8)

        mask_small = cv2.resize(mask, (width, height))
        mask_bgr = cv2.cvtColor(mask_small, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            mask_bgr,
            name,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
        )
        panels.append(mask_bgr)

    return np.hstack(panels)


def open_source(args):
    if args.source == "astra":
        from core.camera_driver import AstraCamera
        cam = AstraCamera()

        def read_frame():
            color, depth = cam.get_frames()
            return True, color, depth

        def release():
            cam.release()

        return read_frame, release

    cap = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    if not cap.isOpened():
        raise RuntimeError(f"无法打开摄像头 index={args.camera_index}")

    def read_frame():
        ok, frame = cap.read()
        return ok, frame, None

    def release():
        cap.release()

    return read_frame, release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["astra", "webcam"], default="astra")
    parser.add_argument("--camera-index", type=int, default=1)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)

    parser.add_argument("--roi", default="0.10,0.20,0.90,0.95")
    parser.add_argument("--min-area-ratio", type=float, default=0.006)

    # 核心参数：超过1m不显示
    parser.add_argument("--max-object-depth-mm", type=int, default=1000)

    # 有效深度范围，用于过滤0值、异常值
    parser.add_argument("--min-valid-depth-mm", type=int, default=300)
    parser.add_argument("--max-valid-depth-mm", type=int, default=2500)
    parser.add_argument("--min-depth-valid-ratio", type=float, default=0.01)

    parser.add_argument(
        "--save-dir",
        default=str(PROJECT_ROOT / "model_training" / "yolo_demo3" / "color_rule_test"),
    )
    args = parser.parse_args()

    roi = parse_roi(args.roi)
    detector = ColorRuleDetector(
        roi=roi,
        min_area_ratio=args.min_area_ratio,
        max_object_depth_mm=args.max_object_depth_mm,
        min_valid_depth_mm=args.min_valid_depth_mm,
        max_valid_depth_mm=args.max_valid_depth_mm,
        min_depth_valid_ratio=args.min_depth_valid_ratio,
    )

    read_frame, release = open_source(args)

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    print("颜色规则 + 深度过滤测试启动")
    print("粉红色 -> apple / 苹果")
    print("黄色 -> banana / 香蕉")
    print("青绿色 -> cucumber / 黄瓜")
    print(f"规则：目标深度超过 {args.max_object_depth_mm}mm 不显示识别结果")
    print("按 s 保存当前检测截图；按 q 退出。")
    print(f"ROI={roi}, min_area_ratio={args.min_area_ratio}")

    try:
        while True:
            ok, frame, depth = read_frame()

            if not ok or frame is None:
                print("读取画面失败")
                break

            if depth is not None and depth.shape[:2] != frame.shape[:2]:
                depth = cv2.resize(
                    depth,
                    (frame.shape[1], frame.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )

            visible_detections, all_candidates, masks = detector.detect(frame, depth)
            drawn = detector.draw(frame, visible_detections, all_candidates)

            if visible_detections:
                best = visible_detections[0]
                depth_info = best["depth"]
                print(
                    f"\r显示目标: {best['display_name']} "
                    f"label={best['label']} conf={best['conf']} "
                    f"depth={depth_info['median_depth_mm']}mm "
                    f"bbox={best['bbox']}       ",
                    end="",
                    flush=True,
                )
            elif all_candidates:
                best = all_candidates[0]
                depth_info = best["depth"]
                print(
                    f"\r隐藏目标: {best['display_name']} "
                    f"reason={depth_info['reason']} "
                    f"depth={depth_info['median_depth_mm']}mm       ",
                    end="",
                    flush=True,
                )
            else:
                print("\r当前目标: 无                         ", end="", flush=True)

            show_main = cv2.resize(drawn, (640, 480))

            depth_vis = depth_to_vis(depth)
            depth_vis = cv2.resize(depth_vis, (320, 240))
            cv2.putText(
                depth_vis,
                "Depth",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
            )

            mask_panel = make_mask_panel(masks, width=213, height=160)
            mask_panel = cv2.resize(mask_panel, (640, 160))

            # 上：检测结果；中：深度图；下：三类颜色mask
            depth_row = cv2.resize(depth_vis, (640, 160))
            show = np.vstack([show_main, depth_row, mask_panel])

            cv2.imshow("Color Rule + Depth Filter Test", show)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("s"):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                out_path = save_dir / f"color_rule_depth_test_{ts}.jpg"
                cv2.imwrite(str(out_path), show)
                print(f"\n已保存截图：{out_path}")

            elif key == ord("q"):
                print("\n用户退出")
                break

    finally:
        release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()