import uuid
from datetime import UTC, datetime
from typing import cast

from noc.orchestration.remediation_nodes import settle_action
from noc.tools.sentinel_client import ActionReply, SentinelClient
from noc_shared.actions import ActionRequest, ActionResult, ActionStatus

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
REQUEST = ActionRequest(
    action_id=uuid.uuid4(),
    attempt_id=uuid.uuid4(),
    incident_id=uuid.uuid4(),
    attempt=1,
    action_hash="a" * 64,
    resource_id="svc:demo-shop",
    auto_policy_ref="policy:test",
)


def result(status: ActionStatus) -> ActionReply:
    return ActionReply(
        "result",
        ActionResult(
            action_id=REQUEST.action_id,
            action_type="start_service",
            resource_id="svc:demo-shop",
            status=status,
            code=None,
            message="m",
            started_at=NOW,
            finished_at=None,
            before=None,
            after=None,
        ),
    )


class FakeClient:
    def __init__(self, posts: list[ActionReply], gets: list[ActionReply]) -> None:
        self.posts = posts
        self.gets = gets
        self.post_calls = 0
        self.get_calls = 0

    async def run_action(self, action_type: str, request: ActionRequest) -> ActionReply:
        self.post_calls += 1
        return self.posts.pop(0)

    async def get_action(self, action_id: uuid.UUID) -> ActionReply:
        self.get_calls += 1
        return self.gets.pop(0)


async def settle(client: FakeClient) -> ActionReply:
    return await settle_action(cast(SentinelClient, client), "start_service", REQUEST)


async def test_a_direct_answer_is_used_without_a_lookup() -> None:
    client = FakeClient([result("succeeded")], [])
    reply = await settle(client)
    assert reply.result is not None
    assert reply.result.status == "succeeded"
    assert client.get_calls == 0


async def test_a_lost_answer_is_read_back_instead_of_resending() -> None:
    client = FakeClient([ActionReply("unknown", detail="timeout")], [result("failed")])
    reply = await settle(client)
    assert reply.result is not None
    assert reply.result.status == "failed"
    assert client.post_calls == 1


async def test_a_request_that_never_arrived_is_sent_once_more_with_the_same_id() -> None:
    client = FakeClient(
        [ActionReply("unknown", detail="reset"), result("succeeded")],
        [ActionReply("not_found")],
    )
    reply = await settle(client)
    assert reply.result is not None
    assert reply.result.status == "succeeded"
    assert client.post_calls == 2


async def test_an_action_still_executing_stays_unknown() -> None:
    client = FakeClient([ActionReply("unknown", detail="timeout")], [result("executing")])
    reply = await settle(client)
    assert reply.kind == "unknown"
    assert client.post_calls == 1


async def test_an_unreachable_lookup_stays_unknown_and_never_resends() -> None:
    client = FakeClient([ActionReply("unknown", detail="timeout")], [ActionReply("unknown")])
    reply = await settle(client)
    assert reply.kind == "unknown"
    assert client.post_calls == 1


async def test_a_missing_action_endpoint_is_reported_as_not_found() -> None:
    client = FakeClient([ActionReply("not_found")], [])
    reply = await settle(client)
    assert reply.kind == "not_found"
    assert client.get_calls == 0
