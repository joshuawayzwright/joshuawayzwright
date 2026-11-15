"""Hands-free mode: wait for "Hey Jarvis", then record the command until the speaker stops talking."""

from __future__ import annotations

import queue
import re
import warnings
from collections.abc import Callable, Iterator
from typing import Any

from .voice import SAMPLE_RATE, VoiceUnavailable, _require

FRAME_SAMPLES = 1_280  # 80 ms at 16 kHz: the frame size openWakeWord is built for
FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE

WAKE_RESIDUE = re.compile(r"^\W*(?:(?:hey|hi|okay|ok|a)\W+)?jarvis\b\W*", re.IGNORECASE)
EXIT_PHRASES = {"goodbye", "goodbye jarvis", "bye", "bye jarvis", "stop listening", "shut down", "exit", "quit"}
CANCEL_PHRASES = {"never mind", "nevermind", "cancel", "forget it", "nothing"}


def strip_wake_word(text: str) -> str:
    """Remove a leading "hey Jarvis" that the recording caught along with the command."""
    return WAKE_RESIDUE.sub("", text, count=1).strip()


def normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).strip().lower()


class Endpointer:
    """Decides when a spoken command starts and ends, from the loudness of each 80 ms frame.

    Speech starts after two consecutive frames above the threshold and ends after `silence_s`
    of quiet. Returns "waiting", "speaking", "done" (speech then silence), or "timeout"
    (no speech within `start_timeout_s`, or the `max_s` cap was reached).
    """

    def __init__(
        self,
        noise_floor: float,
        start_timeout_s: float = 5.0,
        silence_s: float = 1.2,
        max_s: float = 20.0,
        ignore_s: float = 0.25,
    ) -> None:
        self.threshold = max(noise_floor * 3.0, 0.01)
        self.start_timeout = round(start_timeout_s / FRAME_SECONDS)
        self.silence_needed = round(silence_s / FRAME_SECONDS)
        self.max_frames = round(max_s / FRAME_SECONDS)
        self.ignore = round(ignore_s / FRAME_SECONDS)  # skip the chime and the end of the wake word
        self.frames = 0
        self.loud_run = 0
        self.quiet_run = 0
        self.started = False

    def feed(self, rms: float) -> str:
        self.frames += 1
        if self.frames <= self.ignore:
            return "waiting"
        loud = rms >= self.threshold
        if not self.started:
            self.loud_run = self.loud_run + 1 if loud else 0
            if self.loud_run >= 2:
                self.started = True
                return "speaking"
            return "timeout" if self.frames >= self.start_timeout else "waiting"
        self.quiet_run = 0 if loud else self.quiet_run + 1
        if self.quiet_run >= self.silence_needed:
            return "done"
        return "timeout" if self.frames >= self.max_frames else "speaking"


class WakeWordListener:
    """Listens on the microphone for "Hey Jarvis" with openWakeWord (local, offline)."""

    def __init__(self, threshold: float = 0.5, chime: bool = True) -> None:
        self.np = _require("numpy")
        openwakeword = _require("openwakeword")
        from openwakeword.model import Model  # type: ignore[import-not-found]

        try:
            path = openwakeword.models["hey_jarvis"]["model_path"]
        except (AttributeError, KeyError, TypeError) as err:
            raise VoiceUnavailable(
                "This openwakeword version has no bundled 'hey_jarvis' model. "
                'Reinstall with: pip install ".[voice]"'
            ) from err
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*CUDAExecutionProvider.*")
            self.model = Model(wakeword_model_paths=[path])
        self.threshold = threshold
        self.chime = chime
        self.noise_floor = 0.005
        self.sd: Any = None  # loaded on first microphone use, so the frame logic is testable without audio

    # -- Pure frame logic (fed by the microphone, or by a file in tests) ---------------------

    def _rms(self, frame: Any) -> float:
        samples = frame.astype("float32") / 32768.0
        return float(self.np.sqrt(self.np.mean(samples * samples)))

    def _flush(self) -> None:
        """Clear the model's audio history. openWakeWord's reset() only clears scores, so the last
        "Hey Jarvis" would otherwise still be buffered and wake it again straight away."""
        silence = self.np.zeros(FRAME_SAMPLES, dtype="int16")
        for _ in range(round(2.5 / FRAME_SECONDS)):
            self.model.predict(silence)
        self.model.reset()

    def detect(self, frames: Iterator[Any]) -> bool:
        """Consume frames until the wake word is heard. Returns False if the frames run out."""
        self._flush()
        for frame in frames:
            score = max(self.model.predict(frame).values())
            if score >= self.threshold:
                return True
            # Track background noise to set the speech threshold: fall quickly, rise slowly, and
            # ignore frames far above the floor (speech), so talking doesn't raise it.
            rms = self._rms(frame)
            if rms < self.noise_floor:
                self.noise_floor += 0.2 * (rms - self.noise_floor)
            elif rms < self.noise_floor * 3:
                self.noise_floor += 0.05 * (rms - self.noise_floor)
        return False

    def capture(self, frames: Iterator[Any], start_timeout_s: float, ignore_s: float) -> Any:
        """Record one utterance. Returns float32 audio, empty if nobody spoke."""
        endpointer = Endpointer(self.noise_floor, start_timeout_s=start_timeout_s, ignore_s=ignore_s)
        kept: list[Any] = []
        for frame in frames:
            kept.append(frame)
            state = endpointer.feed(self._rms(frame))
            if state in ("done", "timeout"):
                break
        if not endpointer.started:
            return self.np.zeros(0, dtype="float32")
        return self.np.concatenate(kept).astype("float32") / 32768.0

    # -- Microphone ----------------------------------------------------------------------------

    def _mic_frames(self, frames: queue.Queue) -> Iterator[Any]:
        while True:
            yield frames.get()

    def _open_stream(self, frames: queue.Queue) -> Any:
        if self.sd is None:
            self.sd = _require("sounddevice")

        def callback(indata: Any, n: int, time: Any, status: Any) -> None:
            frames.put(indata[:, 0].copy())

        return self.sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES, callback=callback
        )

    def _play_chime(self) -> None:
        if not self.chime:
            return
        t = self.np.arange(int(SAMPLE_RATE * 0.12)) / SAMPLE_RATE
        tone = 0.2 * self.np.sin(2 * self.np.pi * 880 * t) * self.np.hanning(t.size)
        self.sd.play(tone.astype("float32"), SAMPLE_RATE)  # non-blocking

    def wait_for_command(self, on_wake: Callable[[], None] = lambda: None) -> Any:
        """Block until "Hey Jarvis", then record and return the command audio."""
        frames: queue.Queue = queue.Queue()
        with self._open_stream(frames):
            source = self._mic_frames(frames)
            self.detect(source)
            on_wake()
            self._play_chime()
            return self.capture(source, start_timeout_s=5.0, ignore_s=0.25)

    def listen_for_follow_up(self, timeout_s: float = 5.0) -> Any:
        """After a reply, record a follow-up question without the wake word. Empty if none."""
        frames: queue.Queue = queue.Queue()
        with self._open_stream(frames):
            return self.capture(self._mic_frames(frames), start_timeout_s=timeout_s, ignore_s=0.0)
