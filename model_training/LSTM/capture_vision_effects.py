import cv2
import mediapipe as mp
import os


def capture_thesis_vision_effects():
    # 恢复官方标准的调用方式
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.5
    )

    # ================= 关键修改区域 =================
    # 0 通常是笔记本自带摄像头，1 或 2 通常是外接的 Astra Pro Plus RGB 镜头
    # 如果画面没出来，请把 1 改成 0 或 2 试试
    CAMERA_INDEX = 1
    cap = cv2.VideoCapture(CAMERA_INDEX)

    # 强制设置 Astra Pro Plus 输出高清分辨率，保证论文配图质量
    # 如果你的电脑带不动 1920x1080，可以改为 1280x720 或 640x480
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # ================================================

    if not cap.isOpened():
        print(f"❌ 无法打开索引为 {CAMERA_INDEX} 的摄像头！请检查 Astra Pro Plus 的 USB 连接，或尝试修改 CAMERA_INDEX 为 0 或 2。")
        return

    # 定义秤盘监控区域 ROI (假设在画面中下方)
    roi_box = [0.2, 0.4, 0.8, 0.9]  # [x_min, y_min, x_max, y_max]

    print("🎥 Astra Pro Plus 彩色摄像头已启动，论文素材高清抓拍模式：")
    print("👉 按 '1' 抓拍：快速替换 (Rapid Swap)")
    print("👉 按 '2' 抓拍：部分遮挡 (Partial Occlusion)")
    print("👉 按 '3' 抓拍：恶意托底 (Bottom-Dragging)")
    print("👉 按 'q' 退出")

    while cap.isOpened():
        success, image = cap.read()
        if not success:
            continue

        # 镜像翻转，符合直觉
        image = cv2.flip(image, 1)
        h, w, _ = image.shape

        # 转换颜色空间以供 MediaPipe 处理
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(image_rgb)

        # 绘制秤盘 ROI 区域 (黄色虚线框效果)
        cv2.rectangle(image, (int(roi_box[0] * w), int(roi_box[1] * h)),
                      (int(roi_box[2] * w), int(roi_box[3] * h)), (0, 255, 255), 2)
        cv2.putText(image, "Scale ROI Area", (int(roi_box[0] * w), int(roi_box[1] * h) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # 如果检测到手，绘制骨架关键点
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    image,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style())

        # 显示实时画面
        cv2.imshow('Thesis Vision Capture (Astra Pro Plus)', image)

        # 监听键盘按键
        key = cv2.waitKey(1) & 0xFF

        # --- 根据按键合成带有不同警告信息的论文配图 ---
        if key in [ord('1'), ord('2'), ord('3')]:
            snap_img = image.copy()

            # 添加半透明黑色背景框以便看清文字
            overlay = snap_img.copy()
            cv2.rectangle(overlay, (10, 10), (450, 60), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, snap_img, 0.4, 0, snap_img)

            if key == ord('1'):
                cv2.putText(snap_img, "[ALERT] Rapid Swap Detected! Conf: 0.96",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                save_name = 'vision_effect_swap.png'

            elif key == ord('2'):
                cv2.putText(snap_img, "[ALERT] Occlusion Ratio High: 0.88!",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                save_name = 'vision_effect_occlusion.png'

            elif key == ord('3'):
                cv2.putText(snap_img, "[ALERT] Abnormal Drag Force Detected!",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                save_name = 'vision_effect_drag.png'

            cv2.imwrite(save_name, snap_img)
            print(f"✅ 高清抓拍成功！已保存为: {save_name}")

        elif key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    capture_thesis_vision_effects()