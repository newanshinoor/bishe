from ultralytics import YOLO
from ultralytics.nn.tasks import DetectionModel
import os

def train_multimodal_yolo():
    print("====== 🚀 部署最高层拦截器 (彻底修复 Dummy Tensor 测试) ======")

    # ======================================================================
    # 🔥 最高层挟持：拦截整个 DetectionModel 的初始化
    # 这样既能让网络构建为 4 通道，又能让 YOLO 的测试假图片也变成 4 通道！
    # ======================================================================
    original_init = DetectionModel.__init__

    def patched_init(self, cfg='yolov8n.yaml', ch=3, *args, **kwargs):
        print(f"\n[🚨 最高层拦截触发] YOLO 企图用 ch={ch} 初始化模型与测试数据！")
        print("[🚨 最高层拦截触发] 已被我方强制修改为 ch=4！\n")
        # 无论上层传什么，强制按照 4 通道去初始化整个类
        original_init(self, cfg, 4, *args, **kwargs)

    # 替换系统原生的检测模型类初始化函数
    DetectionModel.__init__ = patched_init
    # ======================================================================

    print("1. 正在加载 YOLOv8-MobileNetV3-4D 网络拓扑...")
    model = YOLO(r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\ultralytics\ultralytics\yolov8-mobilenetv3-4d.yaml")

    print("2. 开始训练 4D 果蔬识别与新鲜度检测模型...")
    # 启动训练
    results = model.train(
        data=r"D:\pycharmProjects\fruit_recognition_system\model_training\yolo\dataset_4d\fruit_4d.yaml",
        epochs=150,
        imgsz=640,
        batch=16,
        device="0",
        project="fruit_runs",
        name="mobilenet_4d_freshness_final",
        pretrained=False,  # 强制从头训练

        # 【禁用 3通道 专用的色彩增强】
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        bgr=0.0,

        # 【保留空间增强】
        mosaic=1.0,
        degrees=10.0,
        flipud=0.5,
        fliplr=0.5,

        plots=True,
        save=True
    )

    print("\n3. 🎉 训练完成！多模态识别模型已保存！")

if __name__ == '__main__':
    train_multimodal_yolo()