"""Offline tests for voice mode. Microphone, Whisper and speakers are replaced with fakes."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from fakes import FakeStream

import pytest

from jarvis import cli, voice
from jarvis.agent import VOICE_PROMPT, Jarvis
from jarvis.tools import ToolContext


def test_speakable_keeps_code_off_the_voice() -> None:
    reply = (
        "## Result\n"
        "The **entry point** is `cli.main`, see [the docs](https://x.y).\n"
        "- calls read_file\n"
        "```python\nprint('secret code')\n```\n"
        "| a | b |\n|---|---|\n"
        "Done."
    )
    spoken = voice.speakable(reply)
    assert "print" not in spoken and "(code is on screen)" in spoken
    assert spoken.startswith("Result The entry point is cli.main, see the docs.")
    assert "read file" in spoken  # snake_case read naturally, not mangled
    assert "#" not in spoken and "*" not in spoken and "|" not in spoken and "https" not in spoken


def test_speakable_truncates_long_replies_at_a_sentence() -> None:
    spoken = voice.speakable("This is a sentence. " * 200, limit=300)
    assert len(spoken) < 360 and spoken.endswith("sentence. The rest is on screen.")


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_elevenlabs_request_and_playback() -> None:
    sent: list = []
    played: list[bytes] = []

    def opener(request, timeout):
        sent.append(request)
        return FakeResponse(b"\x01\x00\x02\x00")

    speaker = voice.ElevenLabsSpeaker("key123", opener=opener, player=played.append)
    speaker.say("Hello, sir.")

    request = sent[0]
    assert request.full_url == (
        "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb?output_format=pcm_22050"
    )
    assert request.get_method() == "POST"
    assert request.get_header("Xi-api-key") == "key123"
    assert json.loads(request.data) == {"text": "Hello, sir.", "model_id": "eleven_multilingual_v2"}
    assert played == [b"\x01\x00\x02\x00"]


def test_elevenlabs_errors_become_voice_unavailable() -> None:
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    with pytest.raises(voice.VoiceUnavailable, match="401"):
        voice.ElevenLabsSpeaker("k", opener=opener, player=lambda _b: None).say("hi")
    with pytest.raises(voice.VoiceUnavailable):
        voice.ElevenLabsSpeaker("k", voice_id="../evil")


# ---- Voice conversation loop ------------------------------------------------------------


class FakeRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def record(self) -> list[float]:
        self.calls += 1
        return [0.0] * 16_000


class FakeTranscriber:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def transcribe(self, audio: object) -> str:
        return self.texts.pop(0)


class FakeSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)


class FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[dict] = []

    def stream(self, **kwargs: object) -> FakeStream:
        return FakeStream(self.create(**kwargs))

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def make_jarvis(tmp_path: Path, replies: list[str], voice_mode: bool = True) -> tuple[Jarvis, FakeMessages]:
    fake = FakeMessages(replies)
    jarvis = Jarvis(
        ctx=ToolContext(workspace=tmp_path, approve=lambda _q: False),
        client=SimpleNamespace(beta=SimpleNamespace(messages=fake)),
        voice_mode=voice_mode,
        on_text=lambda _t: None,
        on_tool=lambda _l: None,
    )
    return jarvis, fake


def scripted(lines: list[str]):
    def read(_label: str) -> str:
        if not lines:
            raise EOFError
        return lines.pop(0)

    return read


def test_voice_loop_talk_type_mute(tmp_path: Path) -> None:
    jarvis, fake = make_jarvis(tmp_path, ["Pulled it, **sir**.", "Typed answer.", "Silent answer."])
    recorder, speaker = FakeRecorder(), FakeSpeaker()
    io_ = cli.VoiceIO(recorder, FakeTranscriber(["pull the rocket repo", ""]), speaker)

    # Enter (talk) -> answer spoken; Enter with nothing heard -> retry; typed message; mute; typed message.
    code = cli.chat_loop(jarvis, io_, tmp_path, read=scripted(["", "", "what changed?", "/mute", "and now?"]))

    assert code == 0
    assert recorder.calls == 2
    assert [c["messages"][0]["content"] for c in fake.calls[:1]] == ["pull the rocket repo"]
    assert speaker.spoken == ["Pulled it, sir.", "Typed answer."]  # nothing spoken after /mute
    assert fake.calls[0]["system"].endswith(VOICE_PROMPT)


def test_voice_prompt_only_in_voice_mode(tmp_path: Path) -> None:
    jarvis, fake = make_jarvis(tmp_path, ["ok"], voice_mode=False)
    jarvis.ask("hi")
    assert VOICE_PROMPT not in fake.calls[0]["system"]


def test_speak_failure_does_not_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    class Broken:
        def say(self, text: str) -> None:
            raise voice.VoiceUnavailable("ElevenLabs returned 429")

    cli.speak(cli.VoiceIO(FakeRecorder(), FakeTranscriber([]), Broken()), "Hello")
    assert "could not speak the reply" in capsys.readouterr().out


def test_tts_none_needs_no_speaker_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice, "PushToTalkRecorder", FakeRecorder)
    monkeypatch.setattr(voice, "WhisperTranscriber", lambda model, language: FakeTranscriber([]))
    args = SimpleNamespace(whisper_model="tiny.en", language=None, tts="none", voice_id="x")
    assert isinstance(cli.build_voice(args).speaker, voice.NullSpeaker)

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(voice.VoiceUnavailable, match="ELEVENLABS_API_KEY"):
        cli.build_voice(SimpleNamespace(**{**vars(args), "tts": "elevenlabs"}))
