import serial
import threading
import time
import re
from collections import deque
from time import monotonic

class RealTimeScale:
    def __init__(self, port='COM5', baud=115200): # ⚠️ 默认改为你的 COM5 和 115200 波特率
        self.current_weight = 0.0
        self.last_weight = 0.0
        self.pending_weight_diff = 0.0
        self.pending_weight_events = deque(maxlen=128)
        self.data_lock = threading.Lock()
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
                        new_weight = float(match.group())
                        with self.data_lock:
                            self.last_weight = self.current_weight
                            # 只要提取出数字即可，不在驱动层做单位换算。
                            self.current_weight = new_weight
                            # 视频循环可能比串口读取更快。累加变化量并在 get_data()
                            # 中消费一次，避免同一个重量脉冲被重复送入 LSTM 多帧。
                            weight_diff = self.current_weight - self.last_weight
                            self.pending_weight_diff += weight_diff
                            # 同一视频帧之间可能已经发生“拿走再放回”。净变化量会互相抵消，
                            # 因此额外保留每个串口跳变，供快速替换保护层逐条消费。
                            self.pending_weight_events.append(
                                (monotonic(), self.current_weight, weight_diff)
                            )
                except Exception as e:
                    pass
            time.sleep(0.05)  # 20Hz 频率读取

    def get_data(self):
        """返回当前原始重量数值，和变化率"""
        with self.data_lock:
            weight_diff = self.pending_weight_diff
            self.pending_weight_diff = 0.0
            return self.current_weight, weight_diff

    def get_features(self):
        """兼容实时视频循环使用的特征读取接口。"""
        return self.get_data()

    def consume_weight_events(self):
        """返回并清空尚未交给实时轨迹保护层的串口重量跳变。"""
        with self.data_lock:
            events = list(self.pending_weight_events)
            self.pending_weight_events.clear()
            return events

    def close(self):
        self.is_running = False
        if hasattr(self, 'ser'):
            self.ser.close()
