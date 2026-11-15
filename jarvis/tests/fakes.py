"""Stand-ins for the Anthropic SDK's streaming helper, built from create()-style fakes."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any


class FakeStream:
    """Mimics `client.beta.messages.stream(...)`: a context manager yielding text events."""

    def __init__(self, message: Any) -> None:
        self.message = message

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def __iter__(self) -> Iterator[SimpleNamespace]:
        for block in self.message.content:
            if getattr(block, "type", "") == "text":
                # Stream each text block in two chunks, like real deltas.
                half = len(block.text) // 2
                yield SimpleNamespace(type="text", text=block.text[:half])
                yield SimpleNamespace(type="text", text=block.text[half:])

    def get_final_message(self) -> Any:
        return self.message


def stream_from(create: Callable[..., Any]) -> Callable[..., FakeStream]:
    return lambda **kwargs: FakeStream(create(**kwargs))
