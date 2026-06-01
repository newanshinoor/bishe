# model_training/LSTM/preprocess.py
import numpy as np
from collections import deque

class DataAligner:
    def __init__(self, window_size=60):
        # 使用双端队列维护滑动窗口
        self.buffer = deque(maxlen=window_size)

    def update(self, vision_features, scale_data):
        """
        vision_features: [x, y, dist, occ]
        scale_data: [weight, weight_diff]
        """
        # 合并为 6 维特征向量
        combined = np.array(vision_features + list(scale_data), dtype=np.float32)
        self.buffer.append(combined)

    def get_sequence(self):
        """返回适合 LSTM 输入的矩阵 (60, 6)"""
        if len(self.buffer) < 60:
            return None
        return np.array(self.buffer)