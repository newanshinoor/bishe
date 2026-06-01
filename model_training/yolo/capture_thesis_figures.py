from openni import openni2
import numpy as np
import cv2
import os

# ================= 配置区 =================
OPENNI2_DIR = r"D:\pycharmProjects\fruit_recognition_system\backend_fastapi"
SAVE_DIR = "./thesis_figures"
os.makedirs(SAVE_DIR, exist_ok=True)

# ================= 初始化相机 =================
openni2.initialize(OPENNI2_DIR)
dev = openni2.Device.open_any()

depth_stream = dev.create_depth_stream()
depth_stream.start()
depth_stream.set_mirroring_enabled(False)

# 🔥 极其重要：硬件级对齐与同步，这是你论文的卖点
dev.set_image_registration_mode(openni2.IMAGE_REGISTRATION_DEPTH_TO_COLOR)
dev.set_depth_color_sync_enabled(True)

# RGB 摄像头 (Astra Pro 通常是端口 1)
cap = cv2.VideoCapture(1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("✅ 准备就绪！请将一个【带有明显凹陷或腐烂】的水果放在镜头前。")
print("👉 按下 's' 键，将自动为你生成并保存论文所需的 3 张高清对比图。")
print("👉 按下 'q' 键退出。")

try:
    while True:
        ret, color_frame = cap.read()
        if not ret: continue

        frame = depth_stream.read_frame()
        depth_data = frame.get_buffer_as_uint16()
        depth_array = np.ndarray((frame.height, frame.width), dtype=np.uint16, buffer=depth_data)

        # ====== 深度图可视化处理 (仅用于预览和生成论文图) ======
        # 将背景和过远的噪点过滤掉 (假设距离相机 1米 以内的才是有效水果区域)
        depth_array = np.clip(depth_array, 0, 1000)

        # 归一化到 0-255 并涂上伪彩色 (学术界最爱用的 JET 或 VIRIDIS)
        depth_norm = cv2.normalize(depth_array, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        depth_colormap = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

        # ====== 生成叠加对齐图 (RGB 叠上 50% 透明度的深度图) ======
        aligned_overlay = cv2.addWeighted(color_frame, 0.6, depth_colormap, 0.4, 0)

        # 显示画面
        cv2.imshow("1. RGB (Press 's' to save)", color_frame)
        cv2.imshow("2. Depth Colormap", depth_colormap)
        cv2.imshow("3. Aligned Overlay", aligned_overlay)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            # 保存用于论文的 3 张核心配图
            cv2.imwrite(os.path.join(SAVE_DIR, "1_RGB_Original.jpg"), color_frame)
            cv2.imwrite(os.path.join(SAVE_DIR, "2_Depth_Colormap.jpg"), depth_colormap)
            cv2.imwrite(os.path.join(SAVE_DIR, "3_Aligned_Overlay.jpg"), aligned_overlay)
            print(f"🎉 成功保存！请去 {SAVE_DIR} 文件夹查看你的论文插图！")

        elif key == ord('q'):
            break

finally:
    depth_stream.stop()
    openni2.unload()
    cap.release()
    cv2.destroyAllWindows()