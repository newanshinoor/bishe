import cv2
import numpy as np

# ================= 1. 配置要验证的图片路径 =================
# 挑一张你刚才处理过的原图和它生成的深度图
RGB_PATH = r"D:\pycharmProjects\fruit_recognition_system\model_training\input_rgb\blemishFruits\blemishApple4.jpg"
DEPTH_PATH = r"D:\pycharmProjects\fruit_recognition_system\model_training\output_depth\blemishFruits\blemishApple4.png"

# ================= 2. 读取数据 =================
# 读取彩色原图
img_rgb = cv2.imread(RGB_PATH)
# 【关键】必须加上 cv2.IMREAD_ANYDEPTH 才能读出真实的 16位 数值
img_depth_16bit = cv2.imread(DEPTH_PATH, cv2.IMREAD_ANYDEPTH)

if img_rgb is None or img_depth_16bit is None:
    print("找不到图片，请检查路径是否正确！")
    exit()

# ================= 3. 转换为伪彩色 (为了肉眼观察) =================
# 先将 16位 (0-65535) 归一化到 8位 (0-255) 范围内
depth_normalized = cv2.normalize(img_depth_16bit, None, 0, 255, cv2.NORM_MINMAX)
depth_8bit = np.uint8(depth_normalized)

# 涂上伪彩色 (JET色带：越近越红，越远越蓝)
depth_colormap = cv2.applyColorMap(depth_8bit, cv2.COLORMAP_JET)

# 为了方便对比，把两张图缩放到一样大小并拼在一起
h, w = img_rgb.shape[:2]
depth_colormap_resized = cv2.resize(depth_colormap, (w, h))
combined_display = np.hstack((img_rgb, depth_colormap_resized))

# ================= 4. 显示结果 =================
# ================= 4. 显示结果 (已增加自适应缩放) =================
window_name = "Left: Original RGB | Right: MiDaS Depth Heatmap"

# 1. 创建一个允许自由缩放的窗口
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

# 2. 强制把窗口初始大小设为 1200x600 (你可以根据屏幕自己改数字)
cv2.resizeWindow(window_name, 1200, 600)

print("正在显示对比图，你可以用鼠标拖拽窗口边缘调整大小，按任意键关闭窗口...")
cv2.imshow(window_name, combined_display)
cv2.waitKey(0)
cv2.destroyAllWindows()