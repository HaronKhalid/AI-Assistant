"""
core/vad.py — Voice Activity Detection
Uses Silero VAD to detect when the user starts and stops speaking.
This prevents recording silence and makes STT much faster.
"""

import numpy as np
import logging
import torch
from collections import deque

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    """
    Silero VAD wrapper.
    Listens to a stream of audio chunks and tells you:
      - when speech STARTS
      - when speech ENDS (silence after speech)
    """

    def __init__(self, config: dict):
        self.cfg = config
        self.sample_rate = config.get("sample_rate", 16000)
        self.threshold = config.get("threshold", 0.5)
        self.min_speech_ms = config.get("min_speech_duration_ms", 300)
        self.min_silence_ms = config.get("min_silence_duration_ms", 800)
        self.max_speech_s = config.get("max_speech_duration_s", 30)

        self._model = None
        self._load_model()

        # State tracking
        self._speech_chunks = []
        self._silence_counter = 0
        self._speech_counter = 0
        self._is_speaking = False

        # Convert ms to chunk counts (chunks are ~80ms each)
        self._chunk_ms = 80
        self._min_speech_chunks = self.min_speech_ms // self._chunk_ms
        self._min_silence_chunks = self.min_silence_ms // self._chunk_ms
        self._max_speech_chunks = int(self.max_speech_s * 1000 / self._chunk_ms)

    def _load_model(self):
        """Load Silero VAD model."""
        try:
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model = model
            self._model.eval()
            logger.info("Silero VAD loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}. Using energy-based VAD.")
            self._model = None

    def is_speech(self, audio_chunk: np.ndarray) -> float:
        """
        Returns speech probability (0.0–1.0) for an audio chunk.
        audio_chunk should be float32, mono, 16kHz.
        """
        if self._model is None:
            return self._energy_vad(audio_chunk)

        try:
            audio_tensor = torch.FloatTensor(audio_chunk)
            if audio_tensor.dim() == 1:
                audio_tensor = audio_tensor.unsqueeze(0)
            with torch.no_grad():
                prob = self._model(audio_tensor, self.sample_rate).item()
            return prob
        except Exception:
            return self._energy_vad(audio_chunk)

    def _energy_vad(self, audio_chunk: np.ndarray) -> float:
        """Fallback: simple energy-based voice detection."""
        energy = np.sqrt(np.mean(audio_chunk ** 2))
        # Normalize to 0-1 range (typical speech energy ~0.01-0.1)
        return min(1.0, energy * 10)

    def process_chunk(self, audio_chunk: np.ndarray):
        """
        Feed an audio chunk. Returns:
          ("speech_start", None)   — user just started speaking
          ("speech_end", audio)    — user finished; returns full speech audio
          ("silence", None)        — nothing happening
          ("recording", None)      — actively recording speech
        """
        prob = self.is_speech(audio_chunk)
        is_speech = prob >= self.threshold

        if not self._is_speaking:
            if is_speech:
                self._speech_counter += 1
                self._speech_chunks.append(audio_chunk)
                if self._speech_counter >= self._min_speech_chunks:
                    self._is_speaking = True
                    self._silence_counter = 0
                    logger.debug("Speech START detected")
                    return ("speech_start", None)
            else:
                # Clear tentative chunks if not enough speech
                if self._speech_counter > 0:
                    self._speech_counter -= 1
                    if self._speech_counter == 0:
                        self._speech_chunks.clear()
            return ("silence", None)

        else:  # Currently recording speech
            self._speech_chunks.append(audio_chunk)

            if not is_speech:
                self._silence_counter += 1
                if self._silence_counter >= self._min_silence_chunks:
                    # Speech ended
                    audio = np.concatenate(self._speech_chunks)
                    self._reset()
                    logger.debug("Speech END detected")
                    return ("speech_end", audio)
            else:
                self._silence_counter = 0

            # Safety: max recording duration
            if len(self._speech_chunks) >= self._max_speech_chunks:
                audio = np.concatenate(self._speech_chunks)
                self._reset()
                logger.warning("Max speech duration reached, forcing end")
                return ("speech_end", audio)

            return ("recording", None)

    def _reset(self):
        self._speech_chunks = []
        self._silence_counter = 0
        self._speech_counter = 0
        self._is_speaking = False
