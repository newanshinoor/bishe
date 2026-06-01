"""
生成 LSTM 防作弊模拟数据集。

特征定义与论文一致，每个样本为 (60, 6)：
    [hand_x, hand_y, hand_dist, occlusion, weight, weight_diff]

类别定义：
    normal     0 正常取放
    swap       1 快速替换
    occlusion  2 部分遮挡
    lift       3 恶意托举/托底
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Dict

import numpy as np


LABELS = ("normal", "swap", "occlusion", "lift")
SEQ_LEN = 60
FPS = 10


def _smooth_segment(length: int, peak: float = 0.8) -> np.ndarray:
    """生成手部接近秤台再离开的平滑距离曲线。"""
    return np.sin(np.linspace(0, np.pi, length)) * peak


def _add_sensor_noise(data: np.ndarray, weight_noise: float = 2.0) -> np.ndarray:
    """添加视觉与重量传感器噪声。"""
    noisy = data.copy()
    noisy[:, :4] += np.random.normal(0, 0.015, noisy[:, :4].shape)
    noisy[:, 4] += np.random.normal(0, weight_noise, noisy[:, 4].shape)
    noisy[:, :4] = np.clip(noisy[:, :4], 0.0, 1.0)
    noisy[:, 5] = np.diff(noisy[:, 4], prepend=noisy[0, 4])
    return noisy.astype(np.float32)


def generate_sample(mode: str = "normal", seq_len: int = SEQ_LEN) -> np.ndarray:
    """
    生成单条模拟样本。

    论文依据：
    - 快速替换：weight_diff 出现强正/负脉冲，手部轨迹短时间往返。
    - 部分遮挡：occlusion 长时间高位平台，但重量没有合理下降。
    - 恶意托举：手部进入 ROI 后重量出现非自然持续减轻或抖动，模拟用户托住商品减小秤面压力。
    """
    if mode not in LABELS:
        raise ValueError(f"Unsupported mode: {mode}")

    base_weight = np.random.uniform(650, 1500)
    hand_x = np.full(seq_len, np.random.uniform(0.45, 0.55), dtype=np.float32)
    hand_y = np.full(seq_len, np.random.uniform(0.55, 0.72), dtype=np.float32)
    hand_dist = np.zeros(seq_len, dtype=np.float32)
    occlusion = np.zeros(seq_len, dtype=np.float32)
    weight = np.full(seq_len, base_weight, dtype=np.float32)

    start_f = np.random.randint(6, 14)
    end_f = np.random.randint(42, 56)
    span = end_f - start_f

    # 轻微自然手部抖动，避免模型只学习常数模板。
    hand_x += np.random.normal(0, 0.025, seq_len)
    hand_y += np.random.normal(0, 0.025, seq_len)

    if mode == "normal":
        # 正常取物：手部平滑靠近，遮挡轻微；重量在拿走时发生一次合理阶跃下降。
        hand_dist[start_f:end_f] = _smooth_segment(span, peak=np.random.uniform(0.55, 0.8))
        occlusion[start_f:end_f] = hand_dist[start_f:end_f] * np.random.uniform(0.15, 0.35)

        drop_f = np.random.randint(start_f + 10, min(end_f, start_f + 24))
        removed_weight = np.random.uniform(120, 420)
        weight[drop_f:] = base_weight - removed_weight
        weight[drop_f:drop_f + 4] += np.linspace(0, -12, min(4, seq_len - drop_f))

    elif mode == "swap":
        # 快速替换：0.5 秒级别内出现抽走-放下，重量先急跌再回升并伴随冲击超调。
        hand_dist[start_f:end_f] = _smooth_segment(span, peak=np.random.uniform(0.65, 0.95))
        occlusion[start_f:end_f] = hand_dist[start_f:end_f] * np.random.uniform(0.25, 0.55)

        event_f = np.random.randint(start_f + 8, min(end_f - 8, start_f + 24))
        low_weight = base_weight - np.random.uniform(250, 650)
        final_weight = base_weight + np.random.uniform(-120, 260)

        weight[event_f:event_f + 3] = np.linspace(base_weight, low_weight, 3)
        weight[event_f + 3:event_f + 7] = np.linspace(low_weight, final_weight + 60, 4)
        weight[event_f + 7:] = final_weight

        hand_x[event_f:event_f + 7] += np.linspace(-0.22, 0.24, 7)
        hand_y[event_f:event_f + 7] += np.linspace(0.16, -0.18, 7)

    elif mode == "occlusion":
        # 部分遮挡：手部关键点持续落入 ROI，遮挡率高位平台；重量没有对应阶跃下降。
        occ_end = min(seq_len, end_f + np.random.randint(4, 10))
        hand_dist[start_f:occ_end] = np.random.uniform(0.62, 0.9)
        hand_x[start_f:occ_end] = np.random.uniform(0.35, 0.65, occ_end - start_f)
        hand_y[start_f:occ_end] = np.random.uniform(0.55, 0.95, occ_end - start_f)
        occlusion[start_f:occ_end] = np.random.uniform(0.72, 0.98, occ_end - start_f)

        # 遮挡物压迫或手掌接触带来小幅噪声，但没有正常取物的阶跃失重。
        weight[start_f:occ_end] += np.cumsum(np.random.normal(0, 3.0, occ_end - start_f))
        weight[occ_end:] = weight[occ_end - 1]

    elif mode == "lift":
        # 恶意托举/托底：用户用手托住商品，秤面读数被持续减轻并出现非自然抖动。
        lift_end = min(seq_len, end_f + np.random.randint(2, 7))
        hand_dist[start_f:lift_end] = np.random.uniform(0.72, 1.0)
        hand_x[start_f:lift_end] = np.random.uniform(0.38, 0.62, lift_end - start_f)
        hand_y[start_f:lift_end] = np.random.uniform(0.62, 0.96, lift_end - start_f)
        occlusion[start_f:lift_end] = np.random.uniform(0.35, 0.7, lift_end - start_f)

        lift_f = np.random.randint(start_f + 5, min(lift_end - 5, start_f + 22))
        support_force = np.random.uniform(120, 420)
        ramp_len = min(8, seq_len - lift_f)
        weight[lift_f:lift_f + ramp_len] = np.linspace(base_weight, base_weight - support_force, ramp_len)
        if lift_f + ramp_len < seq_len:
            tremor_len = seq_len - lift_f - ramp_len
            tremor = np.sin(np.linspace(0, np.pi * 8, tremor_len)) * np.random.uniform(8, 22)
            weight[lift_f + ramp_len:] = base_weight - support_force + tremor

    weight_diff = np.diff(weight, prepend=weight[0])
    data = np.stack([hand_x, hand_y, hand_dist, occlusion, weight, weight_diff], axis=1)
    return _add_sensor_noise(data)


def build_dataset(
    base_path: str | Path = "data/simulated",
    train_counts: Dict[str, int] | None = None,
    val_counts: Dict[str, int] | None = None,
    clean: bool = True,
) -> None:
    """生成训练集和验证集目录。"""
    base_path = Path(base_path)
    train_counts = train_counts or {"normal": 2000, "swap": 1200, "occlusion": 1200, "lift": 1200}
    val_counts = val_counts or {"normal": 500, "swap": 300, "occlusion": 300, "lift": 300}

    if clean and base_path.exists():
        shutil.rmtree(base_path)

    for phase, counts in (("train", train_counts), ("val", val_counts)):
        for label, count in counts.items():
            out_dir = base_path / phase / label
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"生成 {phase}/{label}: {count} 条")
            for i in range(count):
                sample = generate_sample(label)
                np.save(out_dir / f"{label}_{i:05d}.npy", sample)

    print(f"数据集生成完成: {base_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "data" / "simulated"))
    parser.add_argument("--seed", type=int, default=20260601)
    parser.add_argument("--keep", action="store_true", help="保留已有数据，不清空输出目录")
    args = parser.parse_args()

    np.random.seed(args.seed)
    build_dataset(args.out, clean=not args.keep)


if __name__ == "__main__":
    main()
