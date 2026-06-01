# model_training/LSTM/vision_processor.py
import cv2
import mediapipe as mp
import numpy as np


class HandVisionProcessor:
    def __init__(self, roi_box=[0.3, 0.5, 0.7, 0.9]):
        """
        roi_box: [x_min, y_min, x_max, y_max] 归一化后的秤面检测区
        """
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.roi = roi_box
        self.latest_results = None

    def set_roi(self, roi_box):
        """
        更新遮挡检测 ROI。

        roi_box 必须是归一化坐标 [x_min, y_min, x_max, y_max]。
        """
        if len(roi_box) != 4:
            raise ValueError("roi_box must contain 4 values")

        x1, y1, x2, y2 = [float(v) for v in roi_box]
        x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
        y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))

        if x2 - x1 < 0.02 or y2 - y1 < 0.02:
            raise ValueError("roi_box is too small")

        self.roi = [x1, y1, x2, y2]
        return self.roi

    def extract_features(self, frame):
        """
        提取视觉特征: [hand_x, hand_y, hand_dist, occlusion]
        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)
        self.latest_results = results

        # 默认无手状态 (0.5 为屏幕中心，0.0 为无距离/无遮挡)
        hand_x, hand_y, hand_dist, occlusion = 0.5, 0.5, 0.0, 0.0

        if results.multi_hand_landmarks:
            landmarks = results.multi_hand_landmarks[0].landmark

            # 1. 位置特征 (Landmark 9: 中指指根)
            hand_x = landmarks[9].x
            hand_y = landmarks[9].y

            # 2. 深度特征 (利用手掌 0 点到 17 点的像素距离模拟)
            p0 = np.array([landmarks[0].x, landmarks[0].y])
            p17 = np.array([landmarks[17].x, landmarks[17].y])
            hand_size = np.linalg.norm(p0 - p17)
            hand_dist = min(1.0, hand_size * 5.0)

            # 3. 遮挡比例 (统计落在 ROI 内的关键点比例)
            points_in_roi = 0
            for lm in landmarks:
                if self.roi[0] < lm.x < self.roi[2] and self.roi[1] < lm.y < self.roi[3]:
                    points_in_roi += 1
            occlusion = points_in_roi / 21.0

        return [hand_x, hand_y, hand_dist, occlusion]

    def draw_debug_overlay(self, frame):
        """
        在前台调试画面上绘制 MediaPipe 手部关键点、ROI 和遮挡比例。

        遮挡比例严格按照论文定义计算：
            occlusion = ROI 内手部关键点数量 / 21
        """
        output = frame.copy()
        height, width = output.shape[:2]
        x1, y1, x2, y2 = self.roi
        left, top = int(x1 * width), int(y1 * height)
        right, bottom = int(x2 * width), int(y2 * height)

        cv2.rectangle(output, (left, top), (right, bottom), (255, 180, 0), 2)
        cv2.putText(
            output,
            "Occlusion ROI",
            (left, max(20, top - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 180, 0),
            2,
        )

        points_in_roi = 0
        if self.latest_results and self.latest_results.multi_hand_landmarks:
            for hand_landmarks in self.latest_results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    output,
                    hand_landmarks,
                    self.mp_hands.HAND_CONNECTIONS,
                )

                for landmark in hand_landmarks.landmark:
                    point_x = int(landmark.x * width)
                    point_y = int(landmark.y * height)
                    is_inside = x1 < landmark.x < x2 and y1 < landmark.y < y2
                    if is_inside:
                        points_in_roi += 1
                    cv2.circle(
                        output,
                        (point_x, point_y),
                        4,
                        (0, 255, 0) if is_inside else (0, 0, 255),
                        -1,
                    )

        ratio = points_in_roi / 21.0
        cv2.putText(
            output,
            f"ROI landmarks: {points_in_roi}/21 ({ratio:.2f})",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 255, 255),
            2,
        )
        return output
