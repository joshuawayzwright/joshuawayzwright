"""Offline tests for hands-free mode. No microphone or wake-word model is needed."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import cli, wake
from test_voice import FakeSpeaker, FakeTranscriber, make_jarvis


@pytest.mark.parametrize(
    ("heard", "command"),
    [
        ("Hey Jarvis, pull the repo.", "pull the repo."),
        ("jarvis pull the repo", "pull the repo"),
        ("Okay Jarvis... what changed?", "what changed?"),
        ("A Jarvis, list files", "list files"),
        ("Pull Jarvis's repo", "Pull Jarvis's repo"),  # only a leading wake word is removed
    ],
)
def test_strip_wake_word(heard: str, command: str) -> None:
    assert wake.strip_wake_word(heard) == command


def run_endpointer(levels: list[float], **kw: float) -> tuple[str, int]:
    ep = wake.Endpointer(noise_floor=0.002, ignore_s=0.0, **kw)
    for i, rms in enumerate(levels, 1):
        state = ep.feed(rms)
        if state in ("done", "timeout"):
            return state, i
    return state, len(levels)


def test_endpointer_detects_end_of_speech() -> None:
    quiet, loud = 0.002, 0.1
    state, frames = run_endpointer([quiet] * 5 + [loud] * 20 + [quiet] * 30)
    assert state == "done"
    assert frames == 5 + 20 + 15  # ends after 1.2 s (15 frames) of quiet


def test_endpointer_brief_pause_does_not_end_speech() -> None:
    state, _ = run_endpointer([0.1] * 10 + [0.002] * 8 + [0.1] * 10 + [0.002] * 20)
    assert state == "done"
    ep = wake.Endpointer(noise_floor=0.002, ignore_s=0.0)
    states = [ep.feed(x) for x in [0.1] * 10 + [0.002] * 8 + [0.1] * 2]
    assert states[-1] == "speaking"


def test_endpointer_timeouts_and_noise() -> None:
    assert run_endpointer([0.002] * 100, start_timeout_s=2.0) == ("timeout", 25)
    assert run_endpointer([0.1] * 400, max_s=3.0)[0] == "timeout"
    assert run_endpointer([0.002, 0.1, 0.002] * 40, start_timeout_s=2.0)[0] == "timeout"  # single clicks
    assert wake.Endpointer(noise_floor=0.05).threshold == pytest.approx(0.15)  # loud room raises the bar


def test_endpointer_ignores_the_chime() -> None:
    ep = wake.Endpointer(noise_floor=0.002, ignore_s=0.25)
    assert [ep.feed(0.3) for _ in range(3)] == ["waiting"] * 3
    assert not ep.started


def test_detect_flushes_stale_wake_audio() -> None:
    np = pytest.importorskip("numpy")

    class FakeModel:
        def __init__(self) -> None:
            self.silent_frames = 0
            self.resets = 0

        def predict(self, frame):
            if not frame.any():
                self.silent_frames += 1
                return {"hey_jarvis": 0.0}
            return {"hey_jarvis": 0.9 if frame[0] == 7 else 0.0}

        def reset(self) -> None:
            self.resets += 1

    listener = object.__new__(wake.WakeWordListener)
    listener.np, listener.model, listener.threshold, listener.noise_floor = np, FakeModel(), 0.5, 0.005
    frames = [np.full(1280, 50, dtype="int16")] * 3 + [np.full(1280, 7, dtype="int16")]

    assert listener.detect(iter(frames)) is True
    assert listener.model.silent_frames >= 31 and listener.model.resets == 1  # audio history cleared first
    assert listener.noise_floor < 0.005  # adapted toward the quiet background


# ---- Hands-free conversation loop -----------------------------------------------------------


class FakeListener:
    """Returns scripted audio: each item stands for one utterance; [] means silence."""

    def __init__(self, wake_utterances: list, follow_ups: list) -> None:
        self.wake_utterances = wake_utterances
        self.follow_ups = follow_ups
        self.woke = 0

    def wait_for_command(self, on_wake=lambda: None):
        if not self.wake_utterances:
            raise KeyboardInterrupt
        on_wake()
        self.woke += 1
        return self.wake_utterances.pop(0)

    def listen_for_follow_up(self):
        return self.follow_ups.pop(0) if self.follow_ups else []


def voice_io(texts: list[str]) -> cli.VoiceIO:
    return cli.VoiceIO(recorder=SimpleNamespace(), transcriber=FakeTranscriber(texts), speaker=FakeSpeaker())


def test_wake_loop_follow_up_then_sleep(tmp_path: Path) -> None:
    jarvis, fake = make_jarvis(tmp_path, ["It has one commit.", "It was made in August."])
    io_ = voice_io(["Hey Jarvis, how many commits?", "When was it made?", "Hey Jarvis goodbye."])
    listener = FakeListener(wake_utterances=[[1], [1]], follow_ups=[[1], []])

    assert cli.wake_loop(jarvis, io_, listener) == 0

    asked = [m["content"] for m in jarvis.messages if m["role"] == "user"]
    # Wake word stripped; the follow-up needed none; "goodbye" never reached Claude.
    assert asked == ["how many commits?", "When was it made?"]
    assert len(fake.calls) == 2
    assert io_.speaker.spoken == ["It has one commit.", "It was made in August.", "Goodbye."]
    assert listener.woke == 2


def test_wake_loop_cancel_and_unclear(tmp_path: Path) -> None:
    jarvis, fake = make_jarvis(tmp_path, [])
    io_ = voice_io(["", "Never mind."])
    listener = FakeListener(wake_utterances=[[], [1]], follow_ups=[])

    assert cli.wake_loop(jarvis, io_, listener) == 0  # Ctrl+C (fake) after the script ends
    assert fake.calls == [] and io_.speaker.spoken == []
