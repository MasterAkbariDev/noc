import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from noc.orchestration.runtime import IMPLEMENTED_SPECIALISTS, SPECIALIST_PROMPTS
from noc.tools.catalog import build_read_tools
from noc.tools.recorder import MemoryToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.sentinel_client import SentinelDirectory
from noc_sentinel.app import create_app
from noc_sentinel.nonce_store import NonceStore
from noc_sentinel.tools.network import (
    INTERFACES_MAX,
    LISTENING_PORTS_MAX,
    REMOTE_ADDRESSES_MAX,
    NicCounters,
    SocketRow,
    connection_summary,
    interface_stats,
    listening_ports,
    parse_tcp_counters,
    read_optional_int,
)
from noc_shared.signing import sign_request
from noc_shared.tools import (
    ConnectionSummary,
    ListeningPort,
    ListeningPorts,
    NetworkStats,
)
from tests.support.builders import KEY_ID, SECRET, FakeHostReader, FakeSystemctl, sentinel_config

NETWORK_TOOLS = ["get_listening_ports", "get_network_stats", "get_connection_summary"]


def tcp_listener(port: int, pid: int | None = 100, address: str = "192.0.2.1") -> SocketRow:
    return SocketRow(
        proto="tcp",
        local_address=address,
        local_port=port,
        remote_address=None,
        state="LISTEN",
        pid=pid,
    )


def tcp_connection(remote: str, state: str = "ESTABLISHED") -> SocketRow:
    return SocketRow(
        proto="tcp",
        local_address="10.0.0.5",
        local_port=443,
        remote_address=remote,
        state=state,
        pid=200,
    )


def named(pid: int) -> str | None:
    return f"proc-{pid}"


def test_listening_ports_keep_tcp_listeners_and_unconnected_udp_only() -> None:
    rows = [
        tcp_listener(8080),
        tcp_connection("203.0.113.9"),
        SocketRow("udp", "192.0.2.1", 514, None, "NONE", 300),
        SocketRow("udp", "10.0.0.5", 53, "198.51.100.1", "NONE", 301),
    ]
    result = listening_ports(rows, named)
    assert result.ports == [
        ListeningPort(proto="udp", address="192.0.2.1", port=514, process="proc-300"),
        ListeningPort(proto="tcp", address="192.0.2.1", port=8080, process="proc-100"),
    ]
    assert result.truncated is False


def test_listening_ports_are_sorted_by_port() -> None:
    rows = [tcp_listener(9000), tcp_listener(22), tcp_listener(443)]
    assert [port.port for port in listening_ports(rows, named).ports] == [22, 443, 9000]


def test_listening_ports_are_capped_and_marked_truncated() -> None:
    rows = [tcp_listener(port) for port in range(1, LISTENING_PORTS_MAX + 11)]
    result = listening_ports(rows, named)
    assert len(result.ports) == LISTENING_PORTS_MAX
    assert result.ports[-1].port == LISTENING_PORTS_MAX
    assert result.truncated is True


def test_process_name_is_none_when_pid_is_unknown_or_unreadable() -> None:
    rows = [tcp_listener(22, pid=None), tcp_listener(80, pid=4242)]
    result = listening_ports(rows, lambda pid: None)
    assert [port.process for port in result.ports] == [None, None]


def test_process_name_is_clipped_to_200_characters() -> None:
    result = listening_ports([tcp_listener(22)], lambda pid: "p" * 500)
    assert result.ports[0].process == "p" * 200


def test_listening_address_is_clipped_to_200_characters() -> None:
    result = listening_ports([tcp_listener(22, address="a" * 300)], named)
    assert len(result.ports[0].address) == 200


def test_connection_summary_counts_tcp_states_and_ignores_udp() -> None:
    rows = [
        tcp_connection("203.0.113.9", "ESTABLISHED"),
        tcp_connection("203.0.113.10", "CLOSE_WAIT"),
        tcp_listener(443),
        SocketRow("udp", "10.0.0.5", 53, "198.51.100.1", "NONE", 301),
    ]
    summary = connection_summary(rows)
    assert summary.by_state == {"CLOSE_WAIT": 1, "ESTABLISHED": 1, "LISTEN": 1}


def test_connection_summary_excludes_loopback_and_ranks_remote_addresses() -> None:
    rows = [
        tcp_connection("203.0.113.9"),
        tcp_connection("203.0.113.9"),
        tcp_connection("198.51.100.7"),
        tcp_connection("127.0.0.1"),
        tcp_connection("::1"),
    ]
    summary = connection_summary(rows)
    assert [(item.address, item.connections) for item in summary.top_remote_addresses] == [
        ("203.0.113.9", 2),
        ("198.51.100.7", 1),
    ]


def test_connection_summary_caps_remote_addresses_at_ten() -> None:
    rows = [tcp_connection(f"203.0.113.{index}") for index in range(1, 16)]
    summary = connection_summary(rows)
    assert len(summary.top_remote_addresses) == REMOTE_ADDRESSES_MAX


def test_interface_stats_skip_loopback_and_cap_the_list() -> None:
    counters = {"lo": NicCounters(1, 1, 0, 0, 0, 0)}
    counters.update({f"eth{index}": NicCounters(index, index, 1, 2, 3, 4) for index in range(12)})
    stats = interface_stats(counters)
    assert len(stats) == INTERFACES_MAX
    assert all(item.name != "lo" for item in stats)
    assert stats[0].name == "eth0"
    assert stats[0].drops_out == 4


def test_tcp_counters_are_read_from_the_snmp_table() -> None:
    snmp = (
        "Ip: Forwarding DefaultTTL\n"
        "Ip: 1 64\n"
        "Tcp: RtoAlgorithm RtoMin ActiveOpens OutSegs RetransSegs InErrs\n"
        "Tcp: 1 200 1500 90210 37 0\n"
    )
    assert parse_tcp_counters(snmp) == {
        "RtoAlgorithm": 1,
        "RtoMin": 200,
        "ActiveOpens": 1500,
        "OutSegs": 90210,
        "RetransSegs": 37,
        "InErrs": 0,
    }


def test_missing_snmp_table_gives_no_counters() -> None:
    assert parse_tcp_counters(None) == {}
    assert parse_tcp_counters("Ip: 1 64\n") == {}


def test_conntrack_file_is_read_when_present(tmp_path: Path) -> None:
    present = tmp_path / "count"
    present.write_text("1834\n")
    assert read_optional_int(present) == 1834


def test_conntrack_file_is_none_when_absent_or_not_a_number(tmp_path: Path) -> None:
    garbage = tmp_path / "max"
    garbage.write_text("unlimited\n")
    assert read_optional_int(garbage) is None
    assert read_optional_int(tmp_path / "missing") is None


class FakeNetworkReader:
    def __init__(self, ports: int = 1) -> None:
        self.ports = ports

    def listening_ports(self) -> ListeningPorts:
        return listening_ports([tcp_listener(port) for port in range(1, self.ports + 1)], named)

    def stats(self) -> NetworkStats:
        raise AssertionError("stats is not called in these tests")

    def connections(self) -> ConnectionSummary:
        return connection_summary([tcp_connection("203.0.113.9")])


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    config = sentinel_config(tmp_path)
    store = NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300)
    app = create_app(
        config,
        FakeSystemctl(),
        store,
        config.load_secrets(),
        host=FakeHostReader(),
        network=FakeNetworkReader(ports=60),
    )
    return TestClient(app)


def signed_post(client: TestClient, path: str, payload: dict[str, object]):
    body = json.dumps(payload).encode()
    headers = sign_request(KEY_ID, SECRET, "POST", path, body).as_dict()
    return client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})


@pytest.mark.parametrize("tool", NETWORK_TOOLS)
def test_unsigned_network_tool_call_is_rejected(client: TestClient, tool: str) -> None:
    response = client.post(f"/v1/tools/{tool}", json={"args": {}})
    assert response.status_code == 401


def test_listening_ports_are_read_through_signed_request(client: TestClient) -> None:
    body = signed_post(client, "/v1/tools/get_listening_ports", {"args": {}}).json()
    assert body["ok"] is True
    assert len(body["data"]["ports"]) == LISTENING_PORTS_MAX
    assert body["data"]["ports"][0] == {
        "proto": "tcp",
        "address": "192.0.2.1",
        "port": 1,
        "process": "proc-100",
    }
    assert body["data"]["truncated"] is True


def test_connection_summary_is_read_through_signed_request(client: TestClient) -> None:
    body = signed_post(client, "/v1/tools/get_connection_summary", {"args": {}}).json()
    assert body["ok"] is True
    assert body["data"]["by_state"] == {"ESTABLISHED": 1}
    assert body["data"]["top_remote_addresses"] == [{"address": "203.0.113.9", "connections": 1}]


@pytest.mark.parametrize("tool", NETWORK_TOOLS)
def test_network_tools_reject_extra_arguments(client: TestClient, tool: str) -> None:
    body = signed_post(client, f"/v1/tools/{tool}", {"args": {"port": 22}}).json()
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION"


def test_sentinel_lists_the_network_tools(client: TestClient) -> None:
    headers = sign_request(KEY_ID, SECRET, "GET", "/v1/tools", b"").as_dict()
    names = client.get("/v1/tools", headers=headers).json()["tools"]
    assert set(NETWORK_TOOLS) <= set(names)


def test_network_agent_may_call_the_three_network_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(
        build_read_tools(SentinelDirectory(tmp_path, httpx.AsyncClient())),
        MemoryToolCallRecorder(),
    )
    allowed = registry.names_for("network")
    assert set(NETWORK_TOOLS) <= set(allowed)


def test_metrics_agent_may_not_call_the_network_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(
        build_read_tools(SentinelDirectory(tmp_path, httpx.AsyncClient())),
        MemoryToolCallRecorder(),
    )
    assert not set(NETWORK_TOOLS) & set(registry.names_for("metrics"))


def test_runtime_builds_a_network_specialist() -> None:
    assert "network" in IMPLEMENTED_SPECIALISTS
    assert (SPECIALIST_PROMPTS / "network.md").is_file()
