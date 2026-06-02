# model_training/LSTM/preprocess.py
import numpy as np
from collections import deque


# 训练和实时推理统一使用归一化重量特征，降低不同果蔬重量区间带来的分布偏移。
WEIGHT_SCALE_GRAMS = 2000.0
WEIGHT_DIFF_SCALE_GRAMS = 500.0


def normalize_scale_features(weight, weight_diff):
    """将克数转换为适合 LSTM 学习的稳定区间。"""
    normalized_weight = np.clip(float(weight) / WEIGHT_SCALE_GRAMS, 0.0, 1.5)
    normalized_diff = np.clip(float(weight_diff) / WEIGHT_DIFF_SCALE_GRAMS, -1.5, 1.5)
    return normalized_weight, normalized_diff


def normalize_sequence_scale_features(sequence):
    """批量归一化模拟数据中的 weight 和 weight_diff 两列。"""
    normalized = np.asarray(sequence, dtype=np.float32).copy()
    normalized[:, 4] = np.clip(normalized[:, 4] / WEIGHT_SCALE_GRAMS, 0.0, 1.5)
    normalized[:, 5] = np.clip(normalized[:, 5] / WEIGHT_DIFF_SCALE_GRAMS, -1.5, 1.5)
    return normalized


class DataAligner:
    def __init__(self, window_size=60):
        # 使用双端队列维护滑动窗口
        self.window_size = window_size
        self.buffer = deque(maxlen=window_size)

    def update(self, vision_features, scale_data):
        """
        vision_features: [x, y, dist, occ]
        scale_data: [weight, weight_diff]
        """
        # 合并为 6 维特征向量
        normalized_weight, normalized_diff = normalize_scale_features(*scale_data)
        combined = np.array(
            vision_features + [normalized_weight, normalized_diff],
            dtype=np.float32,
        )
        self.buffer.append(combined)

    def get_sequence(self):
        """返回适合 LSTM 输入的矩阵 (60, 6)"""
        if len(self.buffer) < self.window_size:
            return None
        return np.array(self.buffer)

    def reset(self):
        """清空上一轮识别会话的时序数据。"""
        self.buffer.clear()
