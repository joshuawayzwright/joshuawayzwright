"""Streaming replies: live text, and speech that starts at the first finished sentence."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import cli, voice
from jarvis.agent import Jarvis
from jarvis.tools import ToolContext
from test_voice import FakeMessages, FakeRecorder, FakeTranscriber


def feed_in_chunks(text: str, size: int = 5) -> list[str]:
    seg = voice.SentenceSegmenter()
    out: list[str] = []
    for i in range(0, len(text), size):
        out += seg.feed(text[i:i + size])
    return out + seg.flush()


def test_segmenter_splits_sentences_and_skips_code() -> None:
    reply = "All done. Two fixes:\n- `read_file` handles CRLF.\n- Faster tests!\n```bash\nrm -rf build\n```\nAnything else?"
    assert feed_in_chunks(reply) == [
        "All done.", "Two fixes:", "read file handles CRLF.", "Faster tests!", "The code is on screen.", "Anything else?",
    ]


def test_segmenter_handles_split_fences_and_unclosed_code() -> None:
    assert feed_in_chunks("Look:\n``" + "`py\nx = 1\n``" + "`\nDone.", size=3) == ["Look:", "The code is on screen.", "Done."]
    assert feed_in_chunks("Here:\n```\nnever closed") == ["Here:", "The code is on screen."]


def test_segmenter_caps_spoken_length() -> None:
    seg = voice.SentenceSegmenter(limit=40)
    out = seg.feed("First sentence here. Second sentence here. Third sentence here. ") + seg.flush()
    assert out == ["First sentence here.", "The rest is on screen."]


class RecordingSpeaker:
    def __init__(self, fail: bool = False) -> None:
        self.spoken: list[str] = []
        self.fail = fail
        self.stopped = False
        self.threads: set[str] = set()

    def say(self, text: str) -> None:
        self.threads.add(threading.current_thread().name)
        if self.fail:
            raise voice.VoiceUnavailable("quota exceeded")
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped = True


def test_speech_queue_threaded_and_inline() -> None:
    threaded = RecordingSpeaker()
    q = voice.SpeechQueue(threaded)
    for s in ["One.", "Two.", "Three."]:
        q.say(s)
    q.wait()
    assert threaded.spoken == ["One.", "Two.", "Three."] and threaded.threads == {"jarvis-speech"}

    inline = RecordingSpeaker()
    inline.thread_safe = False  # like the pyttsx3 system voice
    voice.SpeechQueue(inline).say("Hi.")
    assert inline.threads == {threading.current_thread().name}


def test_speech_queue_reports_failure_once_and_cancels() -> None:
    errors: list[str] = []
    speaker = RecordingSpeaker(fail=True)
    q = voice.SpeechQueue(speaker, on_error=errors.append)
    q.say("One.")
    q.say("Two.")
    q.wait()
    assert len(errors) == 1 and "quota exceeded" in errors[0]
    q.cancel()
    assert speaker.stopped


def test_agent_streams_deltas(tmp_path: Path) -> None:
    fake = FakeMessages(["Streaming works."])
    chunks: list[str] = []
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=fake)),
                    on_text=lambda _t: None, on_delta=chunks.append)
    assert jarvis.ask("hi") == "Streaming works."
    assert "".join(chunks) == "Streaming works." and len(chunks) == 2
    assert fake.calls[0]["max_tokens"] == 64000


def test_talk_turn_speaks_sentence_by_sentence(tmp_path: Path) -> None:
    fake = FakeMessages(["Pulled it. It has one commit.\n```\nlog\n```\nShall I continue?"])
    printed: list[str] = []
    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=fake)),
                    on_text=lambda _t: None, on_delta=printed.append)
    speaker = RecordingSpeaker()
    io_ = cli.VoiceIO(FakeRecorder(), FakeTranscriber([]), speaker)

    cli.talk_turn(jarvis, io_, "pull it")

    assert speaker.spoken == ["Pulled it.", "It has one commit.", "The code is on screen.", "Shall I continue?"]
    assert "".join(printed).startswith("Pulled it.")  # the screen still gets the full text
    assert jarvis.on_delta == printed.append  # the printer is restored after the turn

    io_.muted = True
    fake.replies.append("Quiet now.")
    cli.talk_turn(jarvis, io_, "again")
    assert speaker.spoken[-1] == "Shall I continue?"


def test_talk_turn_interrupt_cancels_speech(tmp_path: Path) -> None:
    class Exploding:
        def stream(self, **kwargs):
            raise KeyboardInterrupt

    jarvis = Jarvis(ctx=ToolContext(workspace=tmp_path, approve=lambda _q: True),
                    client=SimpleNamespace(beta=SimpleNamespace(messages=Exploding())), on_text=lambda _t: None)
    speaker = RecordingSpeaker()
    with pytest.raises(KeyboardInterrupt):
        cli.talk_turn(jarvis, cli.VoiceIO(FakeRecorder(), FakeTranscriber([]), speaker), "hi")
    assert speaker.stopped
