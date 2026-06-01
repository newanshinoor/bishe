from ultralytics import YOLO

# 尝试用我们刚才写的图纸，搭建出一个空白的 AI 大脑！
try:
    print("⏳ 正在解析自定义多模态网络...")
    model = YOLO('yolov8-mobilenetv3-4d.yaml')
    print("\n🎉 恭喜！你的 4 通道 MobileNetV3 架构解析成功，没有任何语法错误！\n")

    # 打印一下模型的详细参数，看看我们动刀的地方生效了没
    model.info()
except Exception as e:
    print("\n❌ 哎呀，翻车了，报错信息如下：")
    print(e)