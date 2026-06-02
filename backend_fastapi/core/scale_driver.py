from __future__ import annotations

import re
import threading
import time
from collections import deque
from time import monotonic

import serial


class RealTimeScale:
    def __init__(self, port: str = "COM5", baud: int = 115200):
        self.current_weight = 0.0
        self.last_weight = 0.0
        self.pending_weight_diff = 0.0
        self.pending_weight_events = deque(maxlen=128)
        self.data_lock = threading.Lock()
        self.is_running = True
        self.connected = False
        self.ser = None

        try:
            self.ser = serial.Serial(port, baud, timeout=1)
            self.connected = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            print(f"HX711 scale sensor connected to {port} (baud rate {baud})")
        except Exception as exc:
            print(f"Scale sensor connection failed: {exc}")

    def _read_loop(self):
        while self.is_running:
            if self.ser is not None and self.ser.in_waiting:
                try:
                    line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                    match = re.search(r"[-+]?\d*\.\d+|\d+", line)
                    if match:
                        self._record_weight(float(match.group()))
                except Exception:
                    pass
            time.sleep(0.05)

    def _record_weight(self, new_weight: float) -> None:
        with self.data_lock:
            self.last_weight = self.current_weight
            self.current_weight = float(new_weight)
            weight_diff = self.current_weight - self.last_weight
            self.pending_weight_diff += weight_diff
            self.pending_weight_events.append((monotonic(), self.current_weight, weight_diff))

    def get_data(self):
        with self.data_lock:
            weight_diff = self.pending_weight_diff
            self.pending_weight_diff = 0.0
            return self.current_weight, weight_diff

    def get_features(self):
        return self.get_data()

    def consume_weight_events(self):
        with self.data_lock:
            events = list(self.pending_weight_events)
            self.pending_weight_events.clear()
            return events

    def close(self):
        self.is_running = False
        self.connected = False
        if self.ser is not None:
            self.ser.close()
