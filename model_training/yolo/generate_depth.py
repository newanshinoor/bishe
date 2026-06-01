import cv2
import torch
import os
import numpy as np

# ================= 1. 配置区 =================
INPUT_DIR = r"C:\Users\饶程\Desktop\yolov8_freshnessDETECTION\train\images"  # 存放纯RGB照片的文件夹
OUTPUT_DIR = r"D:\pycharmProjects\fruit_recognition_system\model_training\output_depth\train_depth"  # 保存生成深度图的文件夹
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================= 2. 加载 MiDaS 模型 =================
print("正在从 PyTorch Hub 下载/加载 MiDaS 模型 (首次运行需联网下载约 100MB)...")
# model_type 选项: "DPT_Large" (最准最慢), "DPT_Hybrid" (均衡), "MiDaS_small" (最快)
model_type = "DPT_Hybrid"  # 毕设做数据增强，small 版本足够用了

midas = torch.hub.load("intel-isl/MiDaS", model_type, trust_repo=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"当前使用的计算设备是: {device}")
midas.to(device)
midas.eval()

# 加载对应的图像预处理模块
midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)

if model_type == "DPT_Large" or model_type == "DPT_Hybrid":
    transform = midas_transforms.dpt_transform
else:
    transform = midas_transforms.small_transform

# ================= 3. 批量处理图片 =================
image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
total = len(image_files)

for i, img_name in enumerate(image_files):
    img_path = os.path.join(INPUT_DIR, img_name)

    # 用 OpenCV 读取图片 (默认是 BGR 格式)
    # 用 numpy 配合 OpenCV 读取带有中文路径的图片
    img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        continue

    # MiDaS 需要 RGB 格式
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # 预处理并送入设备
    input_batch = transform(img_rgb).to(device)

    # 模型推理 (生成深度)
    with torch.no_grad():
        prediction = midas(input_batch)

        # 把生成的深度图 resize 回原图的物理尺寸
        prediction = torch.nn.functional.interpolate(
            prediction.unsqueeze(1),
            size=img_rgb.shape[:2],
            mode="bicubic",
            align_corners=False,
        ).squeeze()

    # 转回 CPU 和 Numpy 数组
    depth_map = prediction.cpu().numpy()

    # ================= 4. 格式对齐 (核心重点) =================
    # MiDaS 输出的是相对逆深度 (数值可能带有负数或小数)
    # 你的 Astra 相机输出的是 16位真实物理深度 (0~65535)
    # 我们将 AI 深度归一化，并拉伸到 16位 空间，伪装成相机拍出来的样子
    depth_min = depth_map.min()
    depth_max = depth_map.max()

    if depth_max - depth_min > 0:
        # 归一化到 0.0 ~ 1.0
        depth_normalized = (depth_map - depth_min) / (depth_max - depth_min)
        # 反转深度 (因为 MiDaS 默认越近值越大，而真实物理相机越近值越小)
        depth_normalized = 1.0 - depth_normalized
        # 映射到 16位 (这里取个合理范围，比如放大到 10000 代表 1米)
        depth_uint16 = (depth_normalized * 10000).astype(np.uint16)
    else:
        depth_uint16 = np.zeros(img_rgb.shape[:2], dtype=np.uint16)

    # 保存为 16位单通道 PNG
    out_name = img_name.rsplit('.', 1)[0] + ".png"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    cv2.imwrite(out_path, depth_uint16)

    print(f"[{i + 1}/{total}] 已生成深度图: {out_name}")

print("全部处理完成！")