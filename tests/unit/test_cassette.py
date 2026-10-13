import uuid
from pathlib import Path

import pytest

from noc.llm.cassette import CassetteLLM, request_key
from noc.llm.client import CassetteMiss
from noc.llm.fake import ScriptedLLM, answer
from noc.llm.types import CallContext, ChatMessage, LLMRequest, Role


def request_about(incident: uuid.UUID) -> LLMRequest:
    return LLMRequest(
        tier="strong",
        messages=[
            ChatMessage(role=Role.USER, content=f"incident {incident} at 2026-10-13T09:00:00Z")
        ],
        context=CallContext(agent="investigator", incident_id=str(incident)),
    )


def test_keys_ignore_ids_and_timestamps() -> None:
    assert request_key(request_about(uuid.uuid4())) == request_key(request_about(uuid.uuid4()))


async def test_recorded_responses_replay_offline(tmp_path: Path) -> None:
    path = tmp_path / "demo.jsonl"
    recorder = CassetteLLM(path, "record", ScriptedLLM([answer('{"ok": true}')]))
    recorded = await recorder.complete(request_about(uuid.uuid4()))

    replayer = CassetteLLM(path, "replay")
    replayed = await replayer.complete(request_about(uuid.uuid4()))
    assert replayed.content == recorded.content
    assert replayed.mode == "replay"


async def test_missing_recording_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CassetteMiss):
        await CassetteLLM(tmp_path / "empty.jsonl", "replay").complete(request_about(uuid.uuid4()))
