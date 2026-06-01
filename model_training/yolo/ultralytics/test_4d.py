import torch
import numpy as np
import cv2
import os
from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel

# ==========================================
# 1. 核心补丁：确保模型加载时初始化为 4 通道
# ==========================================
original_init = DetectionModel.__init__


def patched_init(self, cfg='yolov8n.yaml', ch=3, *args, **kwargs):
    original_init(self, cfg, 4, *args, **kwargs)


DetectionModel.__init__ = patched_init


def test_single_image(model_path, img_path, npy_path):
    # 强制加载 4 通道补丁模型
    model = YOLO(model_path)

    # 1. 读取并处理 RGB
    img_bgr = cv2.imread(img_path)
    if img_bgr is None:
        print(f"❌ 无法读取图片: {img_path}")
        return
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_resized = cv2.resize(img_rgb, (640, 640))

    # [H, W, 3] -> [3, 640, 640]
    img_tensor = torch.from_numpy(img_resized).permute(2, 0, 1).float() / 255.0

    # 2. 读取并处理 NPY 深度图
    if not os.path.exists(npy_path):
        print(f"❌ 找不到深度文件: {npy_path}")
        return
    depth = np.load(npy_path).astype(np.float32)
    depth_resized = cv2.resize(depth, (640, 640))

    # 3. 归一化
    if depth_resized.max() > 1.0:
        depth_resized = depth_resized / 65535.0

    # --- 核心修复：强制确保 depth_tensor 为 3 维 [1, 640, 640] ---
    depth_tensor = torch.from_numpy(depth_resized).float()

    if depth_tensor.ndim == 2:
        # 如果是 [640, 640] -> 增加一个通道维 [1, 640, 640]
        depth_tensor = depth_tensor.unsqueeze(0)
    elif depth_tensor.ndim == 3:
        # 如果是 [640, 640, 1] -> 调整为 [1, 640, 640]
        depth_tensor = depth_tensor.permute(2, 0, 1)

    # 确保它一定是 [1, 640, 640]
    depth_tensor = depth_tensor[:1, :, :]

    # 4. 拼接：[3, 640, 640] + [1, 640, 640] = [4, 640, 640]
    # 然后 unsqueeze(0) 增加 Batch 维度，变成 [1, 4, 640, 640]
    try:
        input_4d = torch.cat([img_tensor, depth_tensor], dim=0).unsqueeze(0)

        # 5. 推理 (将 Tensor 移到模型所在设备)
        input_4d = input_4d.to(next(model.model.parameters()).device)
        results = model.predict(source=input_4d, save=True)

        # 6. 打印结果
        for r in results:
            print(f"✅ {os.path.basename(img_path)} 检测结果:")
            for box in r.boxes:
                name = model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                print(f"   - {name}: {conf:.2f}")

    except Exception as e:
        print(f"❌ 拼接或推理失败: {e}")


if __name__ == '__main__':
    # 修改为你自己的路径
    MY_MODEL = r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\best.pt"

    # 测试一组图片（确保图片和 npy 对应）
    test_samples = [
        {
            "img": r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\input_rgb\test\images\freshApple-460-_png.rf.dd16aac1f1b21863eb44be2061a4f595.jpg",
            "npy": r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\dataset_4d\test\freshApple-460-_png.rf.dd16aac1f1b21863eb44be2061a4f595.npy"
        },
        {
            "img": r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\input_rgb\test\images\blemishMango.png",
            "npy": r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\dataset_4d\test\blemishMango.npy"
        }
    ]

    for sample in test_samples:
        if os.path.exists(sample["img"]):
            test_single_image(MY_MODEL, sample["img"], sample["npy"])
        else:
            print(f"⚠️ 跳过不存在的路径: {sample['img']}")