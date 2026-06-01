import cv2
import numpy as np
import os

# ================= 1. 配置路径 =================
# 你存放原始彩色图和深度图的文件夹
RGB_DIR = r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\input_rgb\train\images"
DEPTH_DIR = r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\output_depth\train_depth"
# 融合后的 4 通道数据存放处
OUTPUT_DIR = r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\dataset_4d\train"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================= 2. 遍历并拼接 =================
# 获取深度图文件夹下所有文件
depth_files = [f for f in os.listdir(DEPTH_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

success_count = 0
for depth_file in depth_files:
    # 获取不带后缀的文件名
    base_name = os.path.splitext(depth_file)[0]

    # --- 核心修改：自动匹配彩色图后缀 ---
    rgb_name = None
    # 依次尝试常见的图片格式
    for ext in ['.jpg', '.JPG', '.png', '.PNG', '.jpeg']:
        if os.path.exists(os.path.join(RGB_DIR, base_name + ext)):
            rgb_name = base_name + ext
            break

    if rgb_name is None:
        print(f"⚠️ 跳过：找不到与深度图 {depth_file} 匹配的彩色图。")
        continue

    rgb_path = os.path.join(RGB_DIR, rgb_name)
    depth_path = os.path.join(DEPTH_DIR, depth_file)

    # 1. 读取 RGB 图 (3通道)
    img_rgb = cv2.imdecode(np.fromfile(rgb_path, dtype=np.uint8), cv2.IMREAD_COLOR)

    # 2. 读取深度图 (注意：使用 IMREAD_UNCHANGED 保留位深)
    img_depth = cv2.imdecode(np.fromfile(depth_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    if img_rgb is None or img_depth is None:
        continue

    # 确保深度图是单通道 (如果是3通道深度图，取第一通道)
    if len(img_depth.shape) == 3:
        img_depth = img_depth[:, :, 0]

    # --- 核心改进：深度数据归一化（解决你之前 mAP 波动的问题） ---
    # 如果深度图是 16 位的，将其映射到 0-255，确保四个通道量级一致
    if img_depth.dtype == np.uint16:
        # 线性缩放或简单截断，建议缩放到 0-255 范围
        img_depth = (img_depth / 256).astype(np.uint8)
    elif img_depth.dtype == np.float32:
        img_depth = (img_depth * 255).astype(np.uint8)

    # 确保两张图的高宽完全一致
    if img_rgb.shape[:2] != img_depth.shape[:2]:
        img_depth = cv2.resize(img_depth, (img_rgb.shape[1], img_rgb.shape[0]))

    # 3. 维度变换
    img_depth_expanded = np.expand_dims(img_depth, axis=2)

    # 4. 拼接成 4 通道矩阵
    img_4d = np.concatenate((img_rgb, img_depth_expanded), axis=2)

    # 5. 保存为 .npy
    output_filename = os.path.join(OUTPUT_DIR, base_name + '.npy')
    np.save(output_filename, img_4d)
    success_count += 1

print(f"✅ 处理完成！共融合 {success_count} 张数据，已保存至 {OUTPUT_DIR}")