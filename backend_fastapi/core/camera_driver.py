from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

try:
    from openni import openni2
except Exception:
    openni2 = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MOCK_IMAGE_DIRS = (
    PROJECT_ROOT / "model_training" / "yolo" / "input_rgb" / "test" / "images",
    PROJECT_ROOT / "model_training" / "yolo" / "input_rgb" / "train" / "images",
)


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


def _env_fourcc(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().upper()
    return (value or default)[:4].ljust(4)


class AstraCamera:
    def __init__(self):
        self.cap = None
        self.depth_stream = None
        self.dev = None
        self.openni_initialized = False
        self.is_mock = False
        self.mode = "astra"
        self.mock_image = None
        self.init_error = None
        self.last_color_img = None

        if _env_flag("USE_MOCK_HARDWARE") or _env_flag("MOCK_CAMERA"):
            self._enable_mock("mock hardware enabled")
            return

        try:
            self._initialize_astra()
        except Exception as exc:
            self._release_hardware()
            self.mode = "astra_error"
            self.init_error = str(exc)
            print(f"Astra camera init failed: {exc}")

    def _initialize_astra(self) -> None:
        if openni2 is None:
            raise RuntimeError("OpenNI2 Python package is unavailable")

        sdk_bin_path = self._resolve_openni_path(
            os.getenv("ASTRA_OPENNI_PATH", "").strip() or str(PROJECT_ROOT / "backend_fastapi")
        )
        openni2.initialize(sdk_bin_path)
        self.openni_initialized = True
        self.dev = openni2.Device.open_any()
        self.depth_stream = self.dev.create_depth_stream()
        self.depth_stream.start()
        self.depth_stream.set_mirroring_enabled(False)
        self.dev.set_image_registration_mode(openni2.IMAGE_REGISTRATION_DEPTH_TO_COLOR)
        self.dev.set_depth_color_sync_enabled(True)

        color_port_value = os.getenv("RGB_CAMERA_INDEX") or os.getenv("ASTRA_COLOR_PORT") or "1"
        color_port = int(color_port_value)
        self.cap = cv2.VideoCapture(color_port)
        if not self.cap.isOpened():
            raise RuntimeError(f"color camera port {color_port} cannot be opened")

        requested_width = _env_int("RGB_FRAME_WIDTH", 640)
        requested_height = _env_int("RGB_FRAME_HEIGHT", 480)
        requested_fps = _env_int("RGB_CAMERA_FPS", 30)
        requested_fourcc = _env_fourcc("RGB_CAMERA_FOURCC", "MJPG")

        if not self._configure_rgb_capture(
            requested_width,
            requested_height,
            requested_fps,
            requested_fourcc,
        ):
            print(
                f"RGB {requested_width}x{requested_height} open failed; "
                "falling back to 640x480."
            )
            if not self._configure_rgb_capture(640, 480, requested_fps, requested_fourcc):
                raise RuntimeError("Astra RGB camera cannot provide a readable frame")

        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS) or requested_fps
        print(f"Astra Pro Plus camera ready. RGB={actual_width}x{actual_height}@{actual_fps:.0f}")

    def _configure_rgb_capture(self, width: int, height: int, fps: int, fourcc: str) -> bool:
        if self.cap is None or not self.cap.isOpened():
            return False

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        self.cap.set(cv2.CAP_PROP_FPS, int(fps))

        ok, frame = self.cap.read()
        if not ok or frame is None:
            return False

        actual_height, actual_width = frame.shape[:2]
        if actual_width < int(width * 0.85) or actual_height < int(height * 0.85):
            return False

        self.last_color_img = frame
        return True

    def _resolve_openni_path(self, sdk_bin_path: str) -> str:
        path = Path(sdk_bin_path).expanduser()
        if path.is_absolute():
            return str(path)
        for base in (Path.cwd(), PROJECT_ROOT):
            candidate = (base / path).resolve()
            if candidate.exists():
                return str(candidate)
        return str((PROJECT_ROOT / path).resolve())

    def _resolve_openni_path(self, sdk_bin_path: str) -> str:
        path = Path(sdk_bin_path).expanduser()
        if path.is_absolute():
            return str(path)
        for base in (Path.cwd(), PROJECT_ROOT):
            candidate = (base / path).resolve()
            if candidate.exists():
                return str(candidate)
        return str((PROJECT_ROOT / path).resolve())

    def _enable_mock(self, reason: str) -> None:
        self._release_hardware()
        self.is_mock = True
        self.mode = "mock"

        source = os.getenv("MOCK_CAMERA_SOURCE", "").strip()
        if source:
            source_path = Path(source).expanduser()
            if source_path.is_file():
                image = cv2.imread(str(source_path))
                if image is not None:
                    self.mock_image = image
                else:
                    self.cap = cv2.VideoCapture(str(source_path))

        if self.mock_image is None and (self.cap is None or not self.cap.isOpened()):
            self.mock_image = self._find_default_mock_image()

        print(f"Camera running in MOCK_CAMERA mode ({reason}).")

    def _find_default_mock_image(self):
        for directory in DEFAULT_MOCK_IMAGE_DIRS:
            if not directory.exists():
                continue
            for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                for path in directory.glob(pattern):
                    image = cv2.imread(str(path))
                    if image is not None:
                        return image

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(image, (180, 100), (460, 380), (0, 140, 255), -1)
        cv2.putText(image, "MOCK CAMERA", (190, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        return image

    def _get_mock_frames(self):
        color_img = None
        if self.cap is not None and self.cap.isOpened():
            ok, color_img = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, color_img = self.cap.read()
            if not ok:
                color_img = None

        if color_img is None:
            color_img = self.mock_image.copy()

        depth_img = np.full(color_img.shape[:2], int(os.getenv("MOCK_DEPTH_MM", "900")), dtype=np.uint16)
        return color_img, depth_img

    def get_frames(self):
        if self.is_mock:
            return self._get_mock_frames()

        if self.init_error:
            raise RuntimeError(f"Astra camera is unavailable: {self.init_error}")

        ok, color_img = self.cap.read()
        if ok and color_img is not None:
            self.last_color_img = color_img
        elif self.last_color_img is not None:
            color_img = self.last_color_img.copy()
        else:
            raise RuntimeError("Astra RGB frame read failed")

        try:
            frame = self.depth_stream.read_frame()
            depth_data = np.frombuffer(frame.get_buffer_as_uint16(), dtype=np.uint16)
            depth_img = depth_data.reshape((frame.height, frame.width))
        except Exception as exc:
            raise RuntimeError(f"Astra depth frame read failed: {exc}") from exc

        return color_img, depth_img

    def _release_hardware(self) -> None:
        try:
            if self.depth_stream is not None:
                self.depth_stream.stop()
        except Exception:
            pass
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        try:
            if openni2 is not None and self.openni_initialized:
                openni2.unload()
        except Exception:
            pass
        self.depth_stream = None
        self.cap = None
        self.openni_initialized = False

    def release(self):
        self._release_hardware()
