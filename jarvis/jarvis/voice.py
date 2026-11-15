"""Voice mode: push-to-talk speech input (local Whisper) and spoken replies (system TTS or ElevenLabs)."""

from __future__ import annotations

import json
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

SAMPLE_RATE = 16_000  # Whisper expects 16 kHz mono
MAX_RECORD_SECONDS = 300
MAX_SPOKEN_CHARS = 1_500
ELEVENLABS_DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George": premade, British, male
ELEVENLABS_DEFAULT_MODEL = "eleven_multilingual_v2"
ELEVENLABS_PCM_RATE = 22_050

INSTALL_HINT = 'Install voice support with: pip install ".[voice]"'


class VoiceUnavailable(Exception):
    """Voice mode cannot start; the message says what to install or configure."""


def _require(module: str) -> Any:
    try:
        return __import__(module)
    except ImportError as err:
        raise VoiceUnavailable(f"Missing Python package for voice mode ({module}). {INSTALL_HINT}") from err
    except OSError as err:  # sounddevice raises OSError when the PortAudio system library is absent
        raise VoiceUnavailable(
            f"{module} could not load a system library: {err}. "
            "On Debian/Ubuntu run `sudo apt install libportaudio2`; on macOS, `brew install portaudio`."
        ) from err


# ---- Text preparation --------------------------------------------------------------------


def speakable(text: str, limit: int = MAX_SPOKEN_CHARS) -> str:
    """Turn a Markdown reply into something pleasant to hear. Code stays on screen, not in the voice."""
    text = re.sub(r"```.*?(```|$)", " (code is on screen) ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> link text
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.MULTILINE)  # table rows
    text = re.sub(r"(\*\*|\*|~~)(\S.*?\S|\S)\1", r"\2", text)  # emphasis
    text = re.sub(r"(?<!\w)(__?)(\S.*?\S|\S)\1(?!\w)", r"\2", text)  # _emphasis_, but not snake_case
    text = text.replace("_", " ")  # read_file -> "read file"
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = (cut[: end + 1] if end > limit // 2 else cut) + " The rest is on screen."
    return text


# ---- Speech input ------------------------------------------------------------------------


class Recorder(Protocol):
    def record(self) -> Any: ...


class Transcriber(Protocol):
    def transcribe(self, audio: Any) -> str: ...


class PushToTalkRecorder:
    """Records from the default microphone until the user presses Enter."""

    def __init__(self, wait_for_stop: Callable[[], object] = input) -> None:
        self.sd = _require("sounddevice")
        self.np = _require("numpy")
        self.wait_for_stop = wait_for_stop
        try:
            self.sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        except Exception as err:  # PortAudioError / ValueError when no usable microphone
            raise VoiceUnavailable(f"No usable microphone found: {err}") from err

    def record(self) -> Any:
        chunks: list[Any] = []
        lock = threading.Lock()
        max_chunks = MAX_RECORD_SECONDS * SAMPLE_RATE // 1024

        def callback(indata: Any, frames: int, time: Any, status: Any) -> None:
            with lock:
                if len(chunks) < max_chunks:
                    chunks.append(indata.copy())

        with self.sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=1024, callback=callback):
            self.wait_for_stop()
        with lock:
            if not chunks:
                return self.np.zeros(0, dtype="float32")
            return self.np.concatenate(chunks)[:, 0]


class WhisperTranscriber:
    """Local speech-to-text with faster-whisper. The model downloads once, then runs offline."""

    def __init__(self, model: str = "base.en", language: str | None = None) -> None:
        faster_whisper = _require("faster_whisper")
        self.language = language
        self.model = faster_whisper.WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(self, audio: Any) -> str:
        if len(audio) < SAMPLE_RATE // 4:  # under 0.25 s: nothing useful was said
            return ""
        segments, _info = self.model.transcribe(audio, beam_size=5, vad_filter=True, language=self.language)
        return " ".join(segment.text.strip() for segment in segments).strip()


# ---- Speech output -----------------------------------------------------------------------


class Speaker(Protocol):
    def say(self, text: str) -> None: ...


class NullSpeaker:
    def say(self, text: str) -> None:
        return None


class SystemSpeaker:
    """Offline text-to-speech through the operating system (SAPI5, NSSpeechSynthesizer or eSpeak)."""

    def __init__(self, rate: int = 185) -> None:
        pyttsx3 = _require("pyttsx3")
        try:
            self.engine = pyttsx3.init()
        except Exception as err:  # pyttsx3 raises RuntimeError when no engine (e.g. eSpeak) is installed
            raise VoiceUnavailable(
                f"System text-to-speech is unavailable: {err}. On Linux install espeak-ng, "
                "or use --tts elevenlabs or --tts none."
            ) from err
        self.engine.setProperty("rate", rate)

    thread_safe = False  # pyttsx3 engines must be driven from the thread that created them

    def say(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()

    def stop(self) -> None:
        self.engine.stop()


class ElevenLabsSpeaker:
    """Natural-sounding voice through the ElevenLabs text-to-speech API (needs ELEVENLABS_API_KEY)."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = ELEVENLABS_DEFAULT_VOICE,
        model_id: str = ELEVENLABS_DEFAULT_MODEL,
        opener: Callable[..., Any] = urllib.request.urlopen,
        player: Callable[[bytes], None] | None = None,
    ) -> None:
        if not re.match(r"^[A-Za-z0-9]+$", voice_id):
            raise VoiceUnavailable(f"Invalid ElevenLabs voice ID '{voice_id}'.")
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.opener = opener
        self.player = player or self._play_pcm

    def synthesize(self, text: str) -> bytes:
        query = urllib.parse.urlencode({"output_format": f"pcm_{ELEVENLABS_PCM_RATE}"})
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?{query}",
            data=json.dumps({"text": text, "model_id": self.model_id}).encode("utf-8"),
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:200]
            raise VoiceUnavailable(f"ElevenLabs returned {err.code}: {detail}") from err
        except urllib.error.URLError as err:
            raise VoiceUnavailable(f"Could not reach ElevenLabs: {err.reason}") from err

    @staticmethod
    def _play_pcm(pcm: bytes) -> None:
        sd = _require("sounddevice")
        np = _require("numpy")
        samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
        sd.play(samples, ELEVENLABS_PCM_RATE)
        try:
            sd.wait()
        except KeyboardInterrupt:
            sd.stop()
            raise

    def say(self, text: str) -> None:
        self.player(self.synthesize(text))

    def stop(self) -> None:
        try:
            _require("sounddevice").stop()
        except VoiceUnavailable:
            pass


# ---- Speaking while the reply streams ------------------------------------------------------

SENTENCE_END = re.compile(r"[.!?:](?=\s)\s+|\n\s*\n|\n(?=\s*(?:[-*+]\s|#|\|))")
CODE_MARKER = "The code is on screen."


class SentenceSegmenter:
    """Splits streaming Markdown into speakable sentences as it arrives. Code blocks are skipped
    (one short marker is spoken instead) and speech stops after `limit` characters."""

    def __init__(self, limit: int = MAX_SPOKEN_CHARS) -> None:
        self.buffer = ""
        self.in_code = False
        self.spoken = 0
        self.limit = limit
        self.exhausted = False

    def feed(self, chunk: str) -> list[str]:
        self.buffer += chunk
        out: list[str] = []
        while True:
            if self.in_code:
                end = self.buffer.find("```")
                if end < 0:
                    self.buffer = self.buffer[-2:]  # a closing fence may be split across chunks
                    return out
                self.buffer = self.buffer[end + 3:]
                self.in_code = False
                continue
            fence = self.buffer.find("```")
            region = self.buffer if fence < 0 else self.buffer[:fence]
            match = SENTENCE_END.search(region)
            if match:
                out += self._emit(region[: match.end()])
                self.buffer = self.buffer[match.end():]
                continue
            if fence >= 0:
                out += self._emit(region) + self._emit(CODE_MARKER, raw=True)
                self.buffer = self.buffer[fence + 3:]
                self.in_code = True
                continue
            return out

    def flush(self) -> list[str]:
        rest, self.buffer = self.buffer, ""
        return [] if self.in_code else self._emit(rest)

    def _emit(self, text: str, raw: bool = False) -> list[str]:
        sentence = text.strip() if raw else speakable(text, limit=10_000)
        if not sentence or self.exhausted:
            return []
        if self.spoken + len(sentence) > self.limit:
            self.exhausted = True
            return ["The rest is on screen."]
        self.spoken += len(sentence)
        return [sentence]


class SpeechQueue:
    """Speaks sentences in order. Thread-safe speakers run on a worker thread, so the reply keeps
    streaming to the screen while Jarvis talks; others speak inline as each sentence completes."""

    def __init__(self, speaker: Speaker, on_error: Callable[[str], None] = print) -> None:
        self.speaker = speaker
        self.on_error = on_error
        self.threaded = getattr(speaker, "thread_safe", True)
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.failed = False
        if self.threaded:
            threading.Thread(target=self._worker, name="jarvis-speech", daemon=True).start()

    def _speak(self, text: str) -> None:
        if self.failed:
            return
        try:
            self.speaker.say(text)
        except VoiceUnavailable as err:
            self.failed = True  # report once per reply, then stay quiet
            self.on_error(f"(could not speak the reply: {err})")

    def _worker(self) -> None:
        while True:
            text = self.queue.get()
            try:
                if text is not None:
                    self._speak(text)
            finally:
                self.queue.task_done()

    def say(self, text: str) -> None:
        if self.threaded:
            self.queue.put(text)
        else:
            self._speak(text)

    def wait(self) -> None:
        """Block until everything queued has been spoken."""
        if self.threaded:
            self.queue.join()

    def cancel(self) -> None:
        """Drop queued sentences and stop the current one where the speaker supports it."""
        while True:
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except queue.Empty:
                break
        stop = getattr(self.speaker, "stop", None)
        if stop:
            try:
                stop()
            except Exception:  # noqa: BLE001 - stopping speech is best effort
                pass
        self.failed = False
