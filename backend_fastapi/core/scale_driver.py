from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from time import monotonic

import serial


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


class RealTimeScale:
    def __init__(self, port: str | None = None, baud: int | None = None):
        self.current_weight = 0.0
        self.last_weight = 0.0
        self.pending_weight_diff = 0.0
        self.pending_weight_events = deque(maxlen=128)
        self.data_lock = threading.Lock()
        self.is_running = True
        self.connected = False
        self.ser = None
        self.is_mock = False
        self.mock_index = 0
        self.mock_weights = self._load_mock_weights()

        if _env_flag("USE_MOCK_HARDWARE") or _env_flag("MOCK_SCALE"):
            self.is_mock = True
            self.current_weight = self.mock_weights[0]
            print("Scale sensor running in mock mode.")
            return

        port = port or os.getenv("SCALE_PORT", "COM5")
        baud = int(baud or os.getenv("SCALE_BAUD", "115200"))

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

    def _load_mock_weights(self) -> list[float]:
        sequence = os.getenv("MOCK_WEIGHT_SEQUENCE", "").strip()
        if sequence:
            values = []
            for part in sequence.split(","):
                try:
                    values.append(float(part.strip()))
                except ValueError:
                    pass
            if values:
                return values
        try:
            return [float(os.getenv("MOCK_WEIGHT_GRAMS", "500"))]
        except ValueError:
            return [500.0]

    def _advance_mock_weight(self) -> None:
        if not self.mock_weights:
            self.mock_weights = [500.0]
        value = self.mock_weights[min(self.mock_index, len(self.mock_weights) - 1)]
        self.mock_index += 1
        self._record_weight(value)

    def get_data(self):
        if self.is_mock:
            self._advance_mock_weight()
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
