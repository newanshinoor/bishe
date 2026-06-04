from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


CLASS_INFO = {
    "apple": {
        "display_name": "苹果",
        "draw_color": [180, 105, 255],  # BGR 粉色
    },
    "banana": {
        "display_name": "香蕉",
        "draw_color": [0, 255, 255],  # BGR 黄色
    },
    "cucumber": {
        "display_name": "黄瓜",
        "draw_color": [0, 255, 0],  # BGR 绿色
    },
}


DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "model_training" / "yolo_demo3" / "color_templates"
DEFAULT_PROFILE_PATH = DEFAULT_TEMPLATE_DIR / "color_profiles.json"


def configure_high_res_rgb(
    width: int,
    height: int,
    fps: int,
    fourcc: str,
    align_depth: bool = True,
) -> None:
    """
    在 AstraCamera 初始化前设置 RGB 高分辨率参数。

    注意：
    1. 这里不修改项目主代码，只影响本脚本进程。
    2. 如果 camera_driver.py 支持这些环境变量，则会优先使用高像素。
    3. 如果摄像头不支持指定分辨率，camera_driver.py 可能会自动降级。
    """
    os.environ["RGB_FRAME_WIDTH"] = str(width)
    os.environ["RGB_FRAME_HEIGHT"] = str(height)
    os.environ["RGB_CAMERA_FPS"] = str(fps)
    os.environ["RGB_CAMERA_FOURCC"] = str(fourcc)

    if align_depth:
        os.environ["DEPTH_ALIGN_TO_RGB"] = "1"

    print(
        f"[CAPTURE CONFIG] RGB={width}x{height}@{fps}, "
        f"FOURCC={fourcc}, DEPTH_ALIGN_TO_RGB={os.environ.get('DEPTH_ALIGN_TO_RGB')}"
    )


def parse_roi(roi_text: str) -> list[float]:
    values = [float(x.strip()) for x in roi_text.split(",")]
    if len(values) != 4:
        raise ValueError("ROI格式应为 x1,y1,x2,y2，例如 0.10,0.20,0.90,0.95")

    x1, y1, x2, y2 = values
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("ROI必须是0~1之间的归一化坐标，且 x1<x2、y1<y2")

    return values


def get_roi_box(frame_shape, roi: list[float]) -> tuple[int, int, int, int]:
    h, w = frame_shape[:2]
    x1 = int(roi[0] * w)
    y1 = int(roi[1] * h)
    x2 = int(roi[2] * w)
    y2 = int(roi[3] * h)

    x1 = max(0, min(w - 1, x1))
    y1 = max(0, min(h - 1, y1))
    x2 = max(1, min(w, x2))
    y2 = max(1, min(h, y2))

    return x1, y1, x2, y2


def depth_to_vis(depth: Optional[np.ndarray], min_mm: int = 300, max_mm: int = 2000) -> np.ndarray:
    if depth is None:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    depth_clip = depth.copy()
    depth_clip[depth_clip == 0] = min_mm
    depth_clip = np.clip(depth_clip, min_mm, max_mm)

    norm = ((depth_clip - min_mm) / max(1, max_mm - min_mm) * 255).astype(np.uint8)
    return cv2.applyColorMap(norm, cv2.COLORMAP_JET)


def circular_hue_distance(h: np.ndarray, center: int) -> np.ndarray:
    diff = np.abs(h.astype(np.int32) - int(center))
    return np.minimum(diff, 180 - diff)


def make_hue_ranges(
    center: int,
    span: int,
    s_low: int,
    s_high: int,
    v_low: int,
    v_high: int,
) -> list[dict]:
    """
    根据中心色相和容差生成 HSV 范围。
    OpenCV HSV 中 H 为 0~179，因此要处理红色/粉色跨 0 点的情况。
    """
    center = int(center) % 180
    span = max(1, int(span))

    start = (center - span) % 180
    end = (center + span) % 180

    if start <= end:
        return [
            {
                "lower": [int(start), int(s_low), int(v_low)],
                "upper": [int(end), int(s_high), int(v_high)],
            }
        ]

    return [
        {
            "lower": [0, int(s_low), int(v_low)],
            "upper": [int(end), int(s_high), int(v_high)],
        },
        {
            "lower": [int(start), int(s_low), int(v_low)],
            "upper": [179, int(s_high), int(v_high)],
        },
    ]


def smooth_hue_histogram(hist: np.ndarray) -> np.ndarray:
    """
    对 H 直方图做环形平滑，避免单点噪声导致主色相不稳定。
    """
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32)
    kernel = kernel / kernel.sum()

    extended = np.concatenate([hist[-2:], hist, hist[:2]])
    smoothed = np.convolve(extended, kernel, mode="same")
    return smoothed[2:-2]


def compute_profile_from_roi(
    image_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    h_margin: int,
    max_h_span: int,
    s_margin: int,
    v_margin: int,
    min_s: int,
    min_v: int,
) -> dict:
    """
    从手动框选的商品区域中提取颜色模板。

    改进点：
    1. 不再简单取 H 的最大补集，否则容易生成超宽范围。
    2. 先找主色相峰值，再围绕主色相生成窄范围。
    3. S/V 下限不会低于 min_s/min_v，减少白纸、灰色背景、阴影误识别。
    """
    x, y, w, h = bbox
    roi_bgr = image_bgr[y:y + h, x:x + w]

    if roi_bgr.size == 0:
        raise RuntimeError("框选区域为空")

    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)

    # 过滤低饱和、过暗像素，减少背景/阴影影响
    base_mask = (hsv[:, :, 1] >= min_s) & (hsv[:, :, 2] >= min_v)
    pixels = hsv[base_mask]

    if pixels.size == 0:
        pixels = hsv.reshape(-1, 3)

    h_values = pixels[:, 0].astype(np.uint8)
    s_values = pixels[:, 1].astype(np.uint8)
    v_values = pixels[:, 2].astype(np.uint8)

    hist = np.bincount(h_values, minlength=180).astype(np.float32)
    hist_smooth = smooth_hue_histogram(hist)
    h_peak = int(np.argmax(hist_smooth))

    hue_dist = circular_hue_distance(h_values, h_peak)

    # 自动估计色相范围，但限制最大宽度，避免模板过宽导致三类互相重叠
    auto_span = int(np.percentile(hue_dist, 75)) + h_margin
    h_span = max(h_margin, min(max_h_span, auto_span))

    selected = hue_dist <= h_span

    if np.count_nonzero(selected) >= 30:
        s_selected = s_values[selected]
        v_selected = v_values[selected]
        h_selected = h_values[selected]
    else:
        s_selected = s_values
        v_selected = v_values
        h_selected = h_values

    s_low = max(min_s, int(np.percentile(s_selected, 5)) - s_margin)
    s_high = min(255, int(np.percentile(s_selected, 95)) + s_margin)
    v_low = max(min_v, int(np.percentile(v_selected, 5)) - v_margin)
    v_high = min(255, int(np.percentile(v_selected, 95)) + v_margin)

    ranges = make_hue_ranges(
        center=h_peak,
        span=h_span,
        s_low=s_low,
        s_high=s_high,
        v_low=v_low,
        v_high=v_high,
    )

    return {
        "ranges": ranges,
        "pixel_count": int(pixels.shape[0]),
        "h_peak": int(h_peak),
        "h_span": int(h_span),
        "h_median": int(np.median(h_selected)),
        "s_median": int(np.median(s_selected)),
        "v_median": int(np.median(v_selected)),
    }


def build_mask_from_ranges(hsv_img: np.ndarray, ranges: list[dict]) -> np.ndarray:
    mask_total = np.zeros(hsv_img.shape[:2], dtype=np.uint8)

    for r in ranges:
        lower = np.array(r["lower"], dtype=np.uint8)
        upper = np.array(r["upper"], dtype=np.uint8)
        mask = cv2.inRange(hsv_img, lower, upper)
        mask_total = cv2.bitwise_or(mask_total, mask)

    kernel = np.ones((5, 5), np.uint8)
    mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_CLOSE, kernel, iterations=2)

    return mask_total


def median_depth_in_bbox(
    depth: Optional[np.ndarray],
    bbox: list[int],
    rgb_shape,
    min_valid_depth_mm: int,
    max_valid_depth_mm: int,
    min_depth_valid_ratio: float,
) -> dict:
    if depth is None:
        return {
            "valid": True,
            "median_depth_mm": None,
            "valid_ratio": 0.0,
            "reason": "no_depth_source",
        }

    if depth.shape[:2] != rgb_shape[:2]:
        depth = cv2.resize(
            depth,
            (rgb_shape[1], rgb_shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    dh, dw = depth.shape[:2]
    x1, y1, x2, y2 = bbox

    x1 = max(0, min(dw - 1, int(x1)))
    x2 = max(0, min(dw, int(x2)))
    y1 = max(0, min(dh - 1, int(y1)))
    y2 = max(0, min(dh, int(y2)))

    if x2 <= x1 or y2 <= y1:
        return {
            "valid": False,
            "median_depth_mm": None,
            "valid_ratio": 0.0,
            "reason": "invalid_bbox",
        }

    roi_depth = depth[y1:y2, x1:x2]
    valid_depth = roi_depth[
        (roi_depth >= min_valid_depth_mm)
        & (roi_depth <= max_valid_depth_mm)
    ]

    valid_ratio = float(valid_depth.size / max(1, roi_depth.size))

    if valid_depth.size == 0 or valid_ratio < min_depth_valid_ratio:
        return {
            "valid": False,
            "median_depth_mm": None,
            "valid_ratio": round(valid_ratio, 4),
            "reason": "invalid_depth",
        }

    return {
        "valid": True,
        "median_depth_mm": int(np.median(valid_depth)),
        "valid_ratio": round(valid_ratio, 4),
        "reason": "ok",
    }


def detect_by_profiles(
    frame_bgr: np.ndarray,
    depth: Optional[np.ndarray],
    profiles: dict,
    roi: list[float],
    min_area_ratio: float,
    max_object_depth_mm: int,
    min_valid_depth_mm: int,
    max_valid_depth_mm: int,
    min_depth_valid_ratio: float,
    max_contours_per_class: int,
):
    h, w = frame_bgr.shape[:2]
    full_area = h * w

    if depth is not None and depth.shape[:2] != frame_bgr.shape[:2]:
        depth = cv2.resize(
            depth,
            (w, h),
            interpolation=cv2.INTER_NEAREST,
        )

    rx1, ry1, rx2, ry2 = get_roi_box(frame_bgr.shape, roi)
    frame_roi = frame_bgr[ry1:ry2, rx1:rx2]

    blur = cv2.GaussianBlur(frame_roi, (5, 5), 0)
    hsv_roi = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)

    candidates = []
    masks = {}

    for cls_name, profile in profiles["classes"].items():
        mask = build_mask_from_ranges(hsv_roi, profile["ranges"])
        masks[cls_name] = mask

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        # 不只取最大轮廓，防止背景大色块抢走目标。
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:max_contours_per_class]:
            area = float(cv2.contourArea(contour))

            if area < full_area * min_area_ratio:
                continue

            x, y, bw, bh = cv2.boundingRect(contour)

            if bw < 8 or bh < 8:
                continue

            x1 = rx1 + x
            y1 = ry1 + y
            x2 = x1 + bw
            y2 = y1 + bh
            bbox = [int(x1), int(y1), int(x2), int(y2)]

            depth_info = median_depth_in_bbox(
                depth,
                bbox,
                frame_bgr.shape,
                min_valid_depth_mm,
                max_valid_depth_mm,
                min_depth_valid_ratio,
            )

            if not depth_info["valid"]:
                continue

            if (
                depth_info["median_depth_mm"] is not None
                and depth_info["median_depth_mm"] > max_object_depth_mm
            ):
                continue

            box_area = max(1, bw * bh)
            fill_ratio = min(1.0, area / box_area)
            conf = round(max(0.55, min(0.96, 0.65 + 0.35 * fill_ratio)), 3)

            candidates.append({
                "class_name": cls_name,
                "display_name": profile["display_name"],
                "bbox": bbox,
                "area": area,
                "fill_ratio": round(fill_ratio, 3),
                "conf": conf,
                "depth": depth_info,
                "draw_color": profile.get("draw_color", [0, 255, 0]),
            })

            # 当前类别找到一个合格目标即可
            break

    candidates.sort(key=lambda item: item["area"], reverse=True)

    # 答辩演示阶段默认只取最大的一个商品，避免多个颜色同时触发
    return candidates[:1], masks


def select_roi_scaled(image: np.ndarray, window_name: str, max_width: int = 960) -> tuple[int, int, int, int]:
    """
    高分辨率图像太大时，缩小显示供用户框选，再映射回原图坐标。
    """
    h, w = image.shape[:2]

    if w > max_width:
        scale = max_width / w
        preview_w = max_width
        preview_h = int(h * scale)
        preview = cv2.resize(image, (preview_w, preview_h))
    else:
        scale = 1.0
        preview = image.copy()

    bbox = cv2.selectROI(window_name, preview, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(window_name)

    x, y, bw, bh = bbox

    if bw <= 0 or bh <= 0:
        return 0, 0, 0, 0

    if scale != 1.0:
        x = int(x / scale)
        y = int(y / scale)
        bw = int(bw / scale)
        bh = int(bh / scale)

    x = max(0, min(w - 1, x))
    y = max(0, min(h - 1, y))
    bw = max(1, min(w - x, bw))
    bh = max(1, min(h - y, bh))

    return int(x), int(y), int(bw), int(bh)


def cmd_capture(args):
    configure_high_res_rgb(
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=args.fourcc,
        align_depth=True,
    )

    from core.camera_driver import AstraCamera

    template_dir = Path(args.template_dir)
    raw_dir = template_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    class_name = args.class_name

    if class_name not in CLASS_INFO:
        raise ValueError(f"class-name 只能是 {list(CLASS_INFO.keys())}")

    cam = AstraCamera()

    print(f"开始拍摄 {class_name} 高像素模板图")
    print("按 s 保存当前图片，按 q 退出")

    saved = False

    try:
        while True:
            color, depth = cam.get_frames()

            if depth is not None and depth.shape[:2] != color.shape[:2]:
                depth = cv2.resize(
                    depth,
                    (color.shape[1], color.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )

            show = color.copy()

            cv2.putText(
                show,
                f"Template: {class_name} | RGB={color.shape[1]}x{color.shape[0]} | Press S to save, Q to quit",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
            )

            preview_w = min(960, color.shape[1])
            preview_h = int(color.shape[0] * preview_w / color.shape[1])
            preview = cv2.resize(show, (preview_w, preview_h))

            cv2.imshow("capture high-res color template", preview)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("s"):
                img_path = raw_dir / f"{class_name}.jpg"
                depth_path = raw_dir / f"{class_name}_depth.png"

                cv2.imwrite(str(img_path), color)

                if depth is not None:
                    cv2.imwrite(str(depth_path), depth)

                print(f"已保存 RGB：{img_path}")
                print(f"RGB shape: {color.shape}")

                if depth is not None:
                    print(f"已保存 Depth：{depth_path}")
                    print(f"Depth shape: {depth.shape}, dtype={depth.dtype}")

                saved = True
                break

            if key == ord("q"):
                break

    finally:
        cam.release()
        cv2.destroyAllWindows()

    if not saved:
        print("未保存模板图")


def cmd_build(args):
    template_dir = Path(args.template_dir)
    raw_dir = template_dir / "raw"
    profile_path = Path(args.profile_path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    profiles = {
        "version": 2,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "description": "High-resolution color template profiles generated from Astra RGB samples.",
        "classes": {},
    }

    for cls_name, info in CLASS_INFO.items():
        img_path = raw_dir / f"{cls_name}.jpg"

        if not img_path.exists():
            raise FileNotFoundError(f"缺少模板图：{img_path}")

        image = cv2.imread(str(img_path))

        if image is None:
            raise RuntimeError(f"无法读取图片：{img_path}")

        preview = image.copy()
        cv2.putText(
            preview,
            f"Select ONLY the object color area for {cls_name}, then ENTER",
            (20, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
        )

        bbox = select_roi_scaled(
            preview,
            window_name=f"select_{cls_name}",
            max_width=args.select_preview_width,
        )

        if bbox[2] <= 0 or bbox[3] <= 0:
            raise RuntimeError(f"未给 {cls_name} 框选有效区域")

        profile = compute_profile_from_roi(
            image,
            bbox,
            h_margin=args.h_margin,
            max_h_span=args.max_h_span,
            s_margin=args.s_margin,
            v_margin=args.v_margin,
            min_s=args.min_s,
            min_v=args.min_v,
        )

        profiles["classes"][cls_name] = {
            "display_name": info["display_name"],
            "draw_color": info["draw_color"],
            "template_image": str(img_path),
            "roi_bbox": [int(v) for v in bbox],
            "ranges": profile["ranges"],
            "pixel_count": profile["pixel_count"],
            "h_peak": profile["h_peak"],
            "h_span": profile["h_span"],
            "h_median": profile["h_median"],
            "s_median": profile["s_median"],
            "v_median": profile["v_median"],
        }

        print(f"\n{cls_name} / {info['display_name']} 颜色模板：")
        print(json.dumps(profiles["classes"][cls_name], ensure_ascii=False, indent=2))

    profile_path.write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n颜色模板已保存：{profile_path}")


def cmd_test(args):
    configure_high_res_rgb(
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=args.fourcc,
        align_depth=True,
    )

    from core.camera_driver import AstraCamera

    profile_path = Path(args.profile_path)

    if not profile_path.exists():
        raise FileNotFoundError(f"颜色模板不存在：{profile_path}")

    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    roi = parse_roi(args.roi)

    cam = AstraCamera()
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    print("颜色模板实时检测启动")
    print(f"使用模板：{profile_path}")
    print(f"最大有效深度：{args.max_object_depth_mm} mm")
    print(f"RGB 请求分辨率：{args.width}x{args.height}@{args.fps}, FOURCC={args.fourcc}")
    print("按 s 保存截图，按 q 退出")

    try:
        while True:
            color, depth = cam.get_frames()

            if depth is not None and depth.shape[:2] != color.shape[:2]:
                depth = cv2.resize(
                    depth,
                    (color.shape[1], color.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )

            detections, masks = detect_by_profiles(
                frame_bgr=color,
                depth=depth,
                profiles=profiles,
                roi=roi,
                min_area_ratio=args.min_area_ratio,
                max_object_depth_mm=args.max_object_depth_mm,
                min_valid_depth_mm=args.min_valid_depth_mm,
                max_valid_depth_mm=args.max_valid_depth_mm,
                min_depth_valid_ratio=args.min_depth_valid_ratio,
                max_contours_per_class=args.max_contours_per_class,
            )

            show = color.copy()

            rx1, ry1, rx2, ry2 = get_roi_box(show.shape, roi)
            cv2.rectangle(show, (rx1, ry1), (rx2, ry2), (255, 255, 255), 2)
            cv2.putText(
                show,
                "Color Template ROI",
                (rx1, max(25, ry1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )

            if detections:
                det = detections[0]
                x1, y1, x2, y2 = det["bbox"]
                draw_color = tuple(int(x) for x in det["draw_color"])
                depth_info = det["depth"]

                label = f"{det['display_name']} {det['conf']:.2f}"
                if depth_info["median_depth_mm"] is not None:
                    label += f" {depth_info['median_depth_mm']}mm"

                cv2.rectangle(show, (x1, y1), (x2, y2), draw_color, 2)
                cv2.putText(
                    show,
                    label,
                    (x1, max(25, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    draw_color,
                    2,
                )

                print(
                    f"\r识别：{det['display_name']} conf={det['conf']} "
                    f"depth={depth_info['median_depth_mm']}mm bbox={det['bbox']}       ",
                    end="",
                    flush=True,
                )
            else:
                cv2.putText(
                    show,
                    "No valid color-template target",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2,
                )
                print("\r识别：无                                  ", end="", flush=True)

            depth_vis = depth_to_vis(depth)
            depth_vis = cv2.resize(depth_vis, (960, 180))

            show_preview_w = 960
            show_preview_h = int(show.shape[0] * show_preview_w / show.shape[1])
            show_main = cv2.resize(show, (show_preview_w, show_preview_h))

            combined = np.vstack([show_main, depth_vis])

            cv2.imshow("color template detector test", combined)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("s"):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                out_path = save_dir / f"template_detect_{ts}.jpg"
                cv2.imwrite(str(out_path), combined)
                print(f"\n已保存截图：{out_path}")

            if key == ord("q"):
                print("\n用户退出")
                break

    finally:
        cam.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_capture = sub.add_parser("capture", help="拍摄单个商品高像素颜色模板图")
    p_capture.add_argument("--class-name", required=True, choices=list(CLASS_INFO.keys()))
    p_capture.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    p_capture.add_argument("--width", type=int, default=1280)
    p_capture.add_argument("--height", type=int, default=960)
    p_capture.add_argument("--fps", type=int, default=30)
    p_capture.add_argument("--fourcc", default="MJPG")
    p_capture.set_defaults(func=cmd_capture)

    p_build = sub.add_parser("build", help="从模板图中框选商品并生成颜色配置")
    p_build.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    p_build.add_argument("--profile-path", default=str(DEFAULT_PROFILE_PATH))
    p_build.add_argument("--h-margin", type=int, default=5)
    p_build.add_argument("--max-h-span", type=int, default=18)
    p_build.add_argument("--s-margin", type=int, default=20)
    p_build.add_argument("--v-margin", type=int, default=30)
    p_build.add_argument("--min-s", type=int, default=35)
    p_build.add_argument("--min-v", type=int, default=40)
    p_build.add_argument("--select-preview-width", type=int, default=960)
    p_build.set_defaults(func=cmd_build)

    p_test = sub.add_parser("test", help="实时测试颜色模板识别")
    p_test.add_argument("--profile-path", default=str(DEFAULT_PROFILE_PATH))
    p_test.add_argument("--roi", default="0.10,0.20,0.90,0.95")
    p_test.add_argument("--min-area-ratio", type=float, default=0.002)
    p_test.add_argument("--max-object-depth-mm", type=int, default=1800)
    p_test.add_argument("--min-valid-depth-mm", type=int, default=300)
    p_test.add_argument("--max-valid-depth-mm", type=int, default=2500)
    p_test.add_argument("--min-depth-valid-ratio", type=float, default=0.01)
    p_test.add_argument("--max-contours-per-class", type=int, default=8)
    p_test.add_argument("--width", type=int, default=1280)
    p_test.add_argument("--height", type=int, default=960)
    p_test.add_argument("--fps", type=int, default=30)
    p_test.add_argument("--fourcc", default="MJPG")
    p_test.add_argument("--save-dir", default=str(DEFAULT_TEMPLATE_DIR / "test_screenshots"))
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()