from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# 当前脚本建议放在 backend_fastapi/tools/ 下
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.camera_driver import AstraCamera


def depth_to_vis(depth: np.ndarray, min_mm: int, max_mm: int) -> np.ndarray:
    """把 uint16 深度图转成便于查看的伪彩图。"""
    depth_clip = depth.copy()
    depth_clip[depth_clip == 0] = min_mm
    depth_clip = np.clip(depth_clip, min_mm, max_mm)

    norm = ((depth_clip - min_mm) / max(1, max_mm - min_mm) * 255).astype(np.uint8)
    return cv2.applyColorMap(norm, cv2.COLORMAP_JET)


def depth_valid_mask(depth: np.ndarray, min_mm: int, max_mm: int) -> np.ndarray:
    """有效深度区域：白色有效，黑色无效。"""
    mask = ((depth >= min_mm) & (depth <= max_mm)).astype(np.uint8) * 255
    return mask


def calc_depth_stats(depth: np.ndarray, min_mm: int, max_mm: int) -> dict:
    valid = depth[(depth >= min_mm) & (depth <= max_mm)]
    total = depth.size

    if valid.size == 0:
        return {
            "valid_count": 0,
            "valid_ratio": 0.0,
            "min_depth": "",
            "median_depth": "",
            "max_depth": "",
        }

    return {
        "valid_count": int(valid.size),
        "valid_ratio": round(float(valid.size / total), 4),
        "min_depth": int(valid.min()),
        "median_depth": int(np.median(valid)),
        "max_depth": int(valid.max()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--class-name", required=True, help="apple / banana / cucumber / empty / demo")
    parser.add_argument("--scene", required=True, help="valid_center / lighting / off_scale / occlusion / screen / empty")
    parser.add_argument("--count", type=int, default=80, help="目标采集张数，达到后自动结束")
    parser.add_argument("--min-depth", type=int, default=400, help="有效深度下限，单位 mm")
    parser.add_argument("--max-depth", type=int, default=2500, help="有效深度上限，单位 mm")
    parser.add_argument(
        "--out-root",
        default=str(PROJECT_ROOT / "model_training" / "yolo_demo3" / "capture_raw"),
        help="输出根目录",
    )
    args = parser.parse_args()

    out_root = Path(args.out_root)
    rgb_dir = out_root / "rgb" / args.class_name / args.scene
    depth_dir = out_root / "depth_raw" / args.class_name / args.scene
    depth_vis_dir = out_root / "depth_vis" / args.class_name / args.scene
    mask_dir = out_root / "depth_mask" / args.class_name / args.scene

    for d in [rgb_dir, depth_dir, depth_vis_dir, mask_dir]:
        d.mkdir(parents=True, exist_ok=True)

    stats_path = out_root / "depth_stats.csv"
    write_header = not stats_path.exists()

    cam = AstraCamera()
    saved = 0

    print("开始采集。")
    print("按 s 保存当前帧；按 q 退出。")
    print(f"class={args.class_name}, scene={args.scene}")
    print(f"out={out_root}")

    with open(stats_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "filename",
                "class_name",
                "scene",
                "valid_count",
                "valid_ratio",
                "min_depth",
                "median_depth",
                "max_depth",
            ],
        )
        if write_header:
            writer.writeheader()

        while saved < args.count:
            color, depth = cam.get_frames()

            # 如果驱动没有做尺寸对齐，这里兜底把 depth 对齐到 RGB 尺寸
            if depth.shape[:2] != color.shape[:2]:
                depth = cv2.resize(
                    depth,
                    (color.shape[1], color.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )

            depth_vis = depth_to_vis(depth, args.min_depth, args.max_depth)
            mask = depth_valid_mask(depth, args.min_depth, args.max_depth)

            # 左：RGB；中：深度伪彩图；右：有效深度mask
            show = np.hstack([
                cv2.resize(color, (320, 240)),
                cv2.resize(depth_vis, (320, 240)),
                cv2.cvtColor(cv2.resize(mask, (320, 240)), cv2.COLOR_GRAY2BGR),
            ])

            cv2.putText(
                show,
                f"{args.class_name}/{args.scene} saved={saved}/{args.count}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                show,
                "Press S to save, Q to quit",
                (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
            )

            cv2.imshow("RGB | DepthVis | DepthMask", show)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("s"):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"{args.class_name}_{args.scene}_{ts}"

                rgb_path = rgb_dir / f"{filename}.jpg"
                depth_path = depth_dir / f"{filename}.png"
                depth_vis_path = depth_vis_dir / f"{filename}.jpg"
                mask_path = mask_dir / f"{filename}.jpg"

                cv2.imwrite(str(rgb_path), color)
                cv2.imwrite(str(depth_path), depth)
                cv2.imwrite(str(depth_vis_path), depth_vis)
                cv2.imwrite(str(mask_path), mask)

                stats = calc_depth_stats(depth, args.min_depth, args.max_depth)
                writer.writerow({
                    "filename": filename,
                    "class_name": args.class_name,
                    "scene": args.scene,
                    **stats,
                })
                f.flush()

                saved += 1
                print(
                    f"saved {saved}/{args.count}: {rgb_path.name}, "
                    f"depth_valid_ratio={stats['valid_ratio']}, "
                    f"median_depth={stats['median_depth']}"
                )

            elif key == ord("q"):
                print("用户退出采集。")
                break

    cv2.destroyAllWindows()
    cam.release()
    print(f"采集结束，共保存 {saved} 张。")


if __name__ == "__main__":
    main()