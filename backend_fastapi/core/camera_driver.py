import numpy as np
import cv2
from openni import openni2


class AstraCamera:
    def __init__(self):
        try:
            # 1. 100% 还原你 collect_astradata.py 的初始化路径
            sdk_bin_path = r"D:\pycharmProjects\fruit_recognition_system\backend_fastapi"
            openni2.initialize(sdk_bin_path)
            self.dev = openni2.Device.open_any()

            # 2. 启动深度流
            self.depth_stream = self.dev.create_depth_stream()
            self.depth_stream.start()
            self.depth_stream.set_mirroring_enabled(False)

            # 3. 【同步配置】还原你脚本中的对齐和硬件同步逻辑
            self.dev.set_image_registration_mode(openni2.IMAGE_REGISTRATION_DEPTH_TO_COLOR)
            self.dev.set_depth_color_sync_enabled(True)

            # 4. 【端口锁定】直接锁定你验证过的端口 1，不带任何 DSHOW 后缀
            print("Connecting to Astra color stream (port 1)...")
            self.cap = cv2.VideoCapture(1)

            # 5. 【参数锁定】必须手动强制设置分辨率
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            if not self.cap.isOpened():
                print("Error: Port 1 cannot be opened. Check if the depth camera is connected or occupied by another program.")
            else:
                print("Astra Pro Plus camera ready.")

        except Exception as e:
            print(f"Camera init failed: {e}")

    def get_frames(self):
        # --- 读取彩色帧 ---
        ret, color_img = self.cap.read()
        if not ret or color_img is None:
            # 仅在读取失败时返回空，防止程序崩溃
            color_img = np.zeros((480, 640, 3), dtype=np.uint8)

        # --- 读取深度帧 ---
        d_frame = self.depth_stream.read_frame()
        d_data = np.frombuffer(d_frame.get_buffer_as_uint16(), dtype=np.uint16)
        depth_img = d_data.reshape((d_frame.height, d_frame.width))

        return color_img, depth_img

    def release(self):
        try:
            if hasattr(self, 'depth_stream'): self.depth_stream.stop()
            if hasattr(self, 'cap'): self.cap.release()
            openni2.unload()
        except:
            pass