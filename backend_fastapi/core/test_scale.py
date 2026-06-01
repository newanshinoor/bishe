import serial
import time

# 自动填入你刚才调试成功的端口
SERIAL_PORT = 'COM5'
# 波特率必须与 Arduino 代码中的 Serial.begin(115200) 保持完全一致
BAUD_RATE = 115200


def test_read_scale():
    print("🚀 正在启动称重传感器测试程序...")
    try:
        # 打开串口
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"✅ 成功连接到串口 {SERIAL_PORT}，波特率: {BAUD_RATE}")
        print("⏳ 正在读取实时数据 (按 Ctrl+C 停止)...\n")
        print("-" * 30)

        while True:
            # 检查串口缓冲区是否有数据
            if ser.in_waiting > 0:
                # 读取一行数据，解码并去除首尾空白字符
                raw_data = ser.readline().decode('utf-8', errors='ignore').strip()

                # 过滤掉空行
                if raw_data:
                    print(f"📦 当前传感器读数: {raw_data}")

            # 短暂休眠，避免跑满 CPU，适配 10Hz 左右的采样率
            time.sleep(0.01)

    except serial.SerialException as e:
        print(f"\n❌ 串口打开失败！请排查以下原因：")
        print("1. Arduino 的 USB 线是否松动？")
        print("2. Arduino IDE 的串口监视器是不是忘记关了？")
        print(f"底层报错信息: {e}")
    except KeyboardInterrupt:
        print("\n⏹️ 测试被手动中断，正在关闭串口...")
        if 'ser' in locals() and ser.is_open:
            ser.close()
        print("✅ 串口已安全关闭。")


if __name__ == "__main__":
    test_read_scale()