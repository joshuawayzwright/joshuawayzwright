"""Voice mode: push-to-talk speech input (local Whisper) and spoken replies (system TTS or ElevenLabs)."""

from __future__ import annotations

import json
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

    def say(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()


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
