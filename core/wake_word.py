"""
core/wake_word.py — Wake Word Detection (Fixed for newer openwakeword)
"""

import numpy as np
import logging
import threading
import queue
import sounddevice as sd
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class WakeWordDetector:
    def __init__(self, config: dict):
        self.cfg = config
        self.model_name = config.get("model", "hey_jarvis")
        self.threshold = config.get("threshold", 0.5)
        self.chunk_size = config.get("chunk_size", 1280)
        self.sample_rate = 16000

        self._oww_model = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable] = None
        self._audio_queue = queue.Queue()

        self._load_model()

    def _load_model(self):
        # Strategy 1: Direct model name (newest API)
        try:
            from openwakeword.model import Model
            self._oww_model = Model(
                wakeword_models=[self.model_name],
                inference_framework="onnx"
            )
            logger.info(f"Wake word loaded: '{self.model_name}'")
            return
        except Exception as e:
            logger.debug(f"Strategy 1 failed: {e}")

        # Strategy 2: Try downloading via newer utility
        try:
            import openwakeword
            if hasattr(openwakeword, 'utils'):
                utils = openwakeword.utils
                if hasattr(utils, 'download_model'):
                    utils.download_model(self.model_name)
                elif hasattr(utils, 'download_models'):
                    utils.download_models([self.model_name])
            from openwakeword.model import Model
            self._oww_model = Model(
                wakeword_models=[self.model_name],
                inference_framework="onnx"
            )
            logger.info("Wake word loaded via Strategy 2")
            return
        except Exception as e:
            logger.debug(f"Strategy 2 failed: {e}")

        # Strategy 3: Load without specifying model (uses defaults)
        try:
            from openwakeword.model import Model
            self._oww_model = Model(inference_framework="onnx")
            logger.info("Wake word loaded via Strategy 3 (default models)")
            return
        except Exception as e:
            logger.debug(f"Strategy 3 failed: {e}")

        # Strategy 4: Manually download the ONNX file
        try:
            self._manual_download_model()
            from openwakeword.model import Model
            self._oww_model = Model(
                wakeword_models=[self.model_name],
                inference_framework="onnx"
            )
            logger.info("Wake word loaded via Strategy 4 (manual download)")
            return
        except Exception as e:
            logger.debug(f"Strategy 4 failed: {e}")

        logger.warning(
            "OpenWakeWord unavailable. Run with --no-wake to use Enter key instead."
        )
        self._oww_model = None

    def _manual_download_model(self):
        import requests, os
        import openwakeword
        pkg_dir = os.path.dirname(openwakeword.__file__)
        models_dir = os.path.join(pkg_dir, "resources", "models")
        os.makedirs(models_dir, exist_ok=True)
        model_file = os.path.join(models_dir, f"{self.model_name}.onnx")

        if os.path.exists(model_file):
            return

        urls = [
            f"https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/{self.model_name}.onnx",
            f"https://github.com/dscripka/openWakeWord/releases/latest/download/{self.model_name}.onnx",
        ]
        for url in urls:
            try:
                logger.info(f"Downloading model from {url} ...")
                r = requests.get(url, timeout=60, stream=True)
                if r.status_code == 200:
                    with open(model_file, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    logger.info(f"Model saved to {model_file}")
                    return
            except Exception as e:
                logger.debug(f"Download failed: {e}")
        raise RuntimeError("Could not download wake word model")

    def _audio_callback(self, indata, frames, time, status):
        self._audio_queue.put(indata[:, 0].copy())

    def _detection_loop(self):
        logger.info("Wake word listener running. Say 'Hey Jarvis' to activate.")
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_size,
            callback=self._audio_callback,
        ):
            while self._running:
                try:
                    chunk = self._audio_queue.get(timeout=1.0)
                    if self._oww_model is None:
                        continue
                    audio_int16 = (chunk * 32767).astype(np.int16)
                    prediction = self._oww_model.predict(audio_int16)
                    for model_name, score in prediction.items():
                        if score >= self.threshold:
                            logger.info(f"Wake word detected! score={score:.2f}")
                            self._oww_model.reset()
                            if self._callback:
                                self._callback()
                            break
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Detection error: {e}")

    def start(self, callback: Callable):
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop, daemon=True, name="WakeWordThread"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    @property
    def is_available(self) -> bool:
        return self._oww_model is not None