from openni import openni2
import numpy as np
import cv2
import os

# ================= 配置区 =================
# 1. 替换为你电脑上 OpenNI2 的 Redist 文件夹路径 (包含 OpenNI2.dll)
# 例如 Windows: r"C:\Program Files\OpenNI2\Redist"
OPENNI2_DIR = r"D:\pycharmProjects\fruit_recognition_system\model_training"

# 2. 数据保存路径
SAVE_DIR_RGB = "./dataset/rgb"
SAVE_DIR_DEPTH = "./dataset/depth"
os.makedirs(SAVE_DIR_RGB, exist_ok=True)
os.makedirs(SAVE_DIR_DEPTH, exist_ok=True)

# ================= 初始化 =================
openni2.initialize(OPENNI2_DIR)
dev = openni2.Device.open_any()

# 创建深度流
depth_stream = dev.create_depth_stream()
depth_stream.start()
depth_stream.set_mirroring_enabled(False)

# 【关键设置：开启深度图对齐到彩色图】
# 这保证了 RGB 图上的苹果位置，和深度图上的苹果位置像素级重合！
dev.set_image_registration_mode(openni2.IMAGE_REGISTRATION_DEPTH_TO_COLOR)
# 开启帧同步
dev.set_depth_color_sync_enabled(True)

# 打开 Astra Pro 的 RGB 摄像头 (0通常是电脑自带摄像头，1通常是外接的Astra彩色镜头)
cap = cv2.VideoCapture(1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("相机启动成功！按 's' 保存图像对，按 'q' 退出。")

img_count = 0

try:
    while True:
        # 1. 读取 RGB 彩色帧
        ret, color_frame = cap.read()
        if not ret:
            continue

        # 2. 读取 深度 帧
        frame = depth_stream.read_frame()
        depth_data = frame.get_buffer_as_uint16()

        # 转换深度数据为 numpy 数组 (16位，代表真实的毫米距离)
        depth_array = np.ndarray((frame.height, frame.width), dtype=np.uint16, buffer=depth_data)

        # 3. 深度图伪彩色处理 (仅用于肉眼预览，不用于训练保存)
        # 将 uint16 映射到 0-255，并涂上伪彩色
        depth_preview = cv2.convertScaleAbs(depth_array, alpha=0.05)
        depth_colormap = cv2.applyColorMap(depth_preview, cv2.COLORMAP_JET)

        # 4. 显示画面
        cv2.imshow("Astra Pro Plus - RGB", color_frame)
        cv2.imshow("Astra Pro Plus - Depth Aligned", depth_colormap)

        # 5. 按键交互
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            img_count += 1
            # 格式化文件名，如 0001.jpg
            file_name = f"{img_count:04d}"

            rgb_path = os.path.join(SAVE_DIR_RGB, f"{file_name}.jpg")
            depth_path = os.path.join(SAVE_DIR_DEPTH, f"{file_name}.png")

            # 【重要】保存数据
            cv2.imwrite(rgb_path, color_frame)
            # 深度图必须存为 16位单通道 PNG，保留真实毫米数据
            cv2.imwrite(depth_path, depth_array)

            print(f"已保存第 {img_count} 组数据: {file_name}")

        elif key == ord('q'):
            break

finally:
    # 释放资源
    cap.release()
    depth_stream.stop()
    openni2.unload()
    cv2.destroyAllWindows()