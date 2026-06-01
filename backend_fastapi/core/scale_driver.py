import serial
import threading
import time
import re

class RealTimeScale:
    def __init__(self, port='COM5', baud=115200): # ⚠️ 默认改为你的 COM5 和 115200 波特率
        self.current_weight = 0.0
        self.last_weight = 0.0
        self.is_running = True
        try:
            # 初始化串口连接
            self.ser = serial.Serial(port, baud, timeout=1)
            # 开启后台线程持续读取数据
            threading.Thread(target=self._read_loop, daemon=True).start()
            print(f"HX711 scale sensor connected to {port} (baud rate {baud})")
        except Exception as e:
            print(f"Sensor connection failed: {e}")

    def _read_loop(self):
        while self.is_running:
            if hasattr(self, 'ser') and self.ser.in_waiting:
                try:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    # 使用正则提取纯数字（假设 Arduino 发送格式为 "118.07" 或 "Weight: 118 g"）
                    match = re.search(r"[-+]?\d*\.\d+|\d+", line)
                    if match:
                        self.last_weight = self.current_weight
                        # 🔥 只要提取出数字就行，不要在这里做乘除法！
                        self.current_weight = float(match.group())
                except Exception as e:
                    pass
            time.sleep(0.05)  # 20Hz 频率读取

    def get_data(self):
        """返回当前原始重量数值，和变化率"""
        return self.current_weight, self.current_weight - self.last_weight

    def close(self):
        self.is_running = False
        if hasattr(self, 'ser'):
            self.ser.close()