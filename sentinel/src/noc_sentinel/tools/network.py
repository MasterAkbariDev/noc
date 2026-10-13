import socket
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Protocol

import psutil

from noc_shared.tools import (
    ConnectionSummary,
    InterfaceStats,
    ListeningPort,
    ListeningPorts,
    NetworkStats,
    RemoteCount,
    SocketProto,
)

LISTENING_PORTS_MAX = 50
INTERFACES_MAX = 10
REMOTE_ADDRESSES_MAX = 10
STRING_MAX_CHARS = 200
IGNORED_INTERFACES = frozenset({"lo"})
PROTO_BY_SOCKET_TYPE: dict[socket.SocketKind, SocketProto] = {
    socket.SOCK_STREAM: "tcp",
    socket.SOCK_DGRAM: "udp",
}
SNMP_PATH = Path("/proc/net/snmp")
CONNTRACK_COUNT_PATH = Path("/proc/sys/net/netfilter/nf_conntrack_count")
CONNTRACK_MAX_PATH = Path("/proc/sys/net/netfilter/nf_conntrack_max")


@dataclass(frozen=True)
class SocketRow:
    proto: SocketProto
    local_address: str
    local_port: int
    remote_address: str | None
    state: str
    pid: int | None


@dataclass(frozen=True)
class NicCounters:
    bytes_sent: int
    bytes_recv: int
    errors_in: int
    errors_out: int
    drops_in: int
    drops_out: int


class NetworkReader(Protocol):
    def listening_ports(self) -> ListeningPorts: ...

    def stats(self) -> NetworkStats: ...

    def connections(self) -> ConnectionSummary: ...


class PsutilNetworkReader:
    def listening_ports(self) -> ListeningPorts:
        return listening_ports(socket_rows(), process_name)

    def stats(self) -> NetworkStats:
        tcp = parse_tcp_counters(read_optional_text(SNMP_PATH))
        return NetworkStats(
            interfaces=interface_stats(nic_counters()),
            tcp_retransmitted_segments=tcp.get("RetransSegs"),
            tcp_out_segments=tcp.get("OutSegs"),
            conntrack_count=read_optional_int(CONNTRACK_COUNT_PATH),
            conntrack_max=read_optional_int(CONNTRACK_MAX_PATH),
        )

    def connections(self) -> ConnectionSummary:
        return connection_summary(socket_rows())


def socket_rows() -> list[SocketRow]:
    rows: list[SocketRow] = []
    for connection in psutil.net_connections(kind="inet"):
        proto = PROTO_BY_SOCKET_TYPE.get(connection.type)
        if proto is None or not connection.laddr:
            continue
        rows.append(
            SocketRow(
                proto=proto,
                local_address=connection.laddr.ip,
                local_port=connection.laddr.port,
                remote_address=connection.raddr.ip if connection.raddr else None,
                state=connection.status,
                pid=connection.pid,
            )
        )
    return rows


def nic_counters() -> dict[str, NicCounters]:
    return {
        name: NicCounters(
            bytes_sent=nic.bytes_sent,
            bytes_recv=nic.bytes_recv,
            errors_in=nic.errin,
            errors_out=nic.errout,
            drops_in=nic.dropin,
            drops_out=nic.dropout,
        )
        for name, nic in psutil.net_io_counters(pernic=True).items()
    }


def process_name(pid: int) -> str | None:
    try:
        return psutil.Process(pid).name()
    except psutil.Error:
        return None


def clip(text: str) -> str:
    return text[:STRING_MAX_CHARS]


def is_listening(row: SocketRow) -> bool:
    if row.proto == "tcp":
        return row.state == psutil.CONN_LISTEN
    return row.remote_address is None


def listening_port_process(row: SocketRow, name_of: Callable[[int], str | None]) -> str | None:
    if row.pid is None:
        return None
    name = name_of(row.pid)
    return None if name is None else clip(name)


def listening_ports(
    rows: Iterable[SocketRow], name_of: Callable[[int], str | None]
) -> ListeningPorts:
    listening = sorted(
        (row for row in rows if is_listening(row)),
        key=lambda row: (row.local_port, row.proto),
    )
    return ListeningPorts(
        ports=[
            ListeningPort(
                proto=row.proto,
                address=clip(row.local_address),
                port=row.local_port,
                process=listening_port_process(row, name_of),
            )
            for row in listening[:LISTENING_PORTS_MAX]
        ],
        truncated=len(listening) > LISTENING_PORTS_MAX,
    )


def is_loopback(address: str) -> bool:
    try:
        return ip_address(address).is_loopback
    except ValueError:
        return False


def connection_summary(rows: Iterable[SocketRow]) -> ConnectionSummary:
    tcp_rows = [row for row in rows if row.proto == "tcp"]
    by_state = Counter(row.state for row in tcp_rows)
    remotes = Counter(
        row.remote_address
        for row in tcp_rows
        if row.remote_address is not None and not is_loopback(row.remote_address)
    )
    top_remotes = sorted(remotes.items(), key=lambda item: (-item[1], item[0]))
    return ConnectionSummary(
        by_state=dict(sorted(by_state.items())),
        top_remote_addresses=[
            RemoteCount(address=clip(address), connections=count)
            for address, count in top_remotes[:REMOTE_ADDRESSES_MAX]
        ],
    )


def interface_stats(counters: Mapping[str, NicCounters]) -> list[InterfaceStats]:
    return [
        InterfaceStats(
            name=clip(name),
            bytes_sent=nic.bytes_sent,
            bytes_recv=nic.bytes_recv,
            errors_in=nic.errors_in,
            errors_out=nic.errors_out,
            drops_in=nic.drops_in,
            drops_out=nic.drops_out,
        )
        for name, nic in sorted(counters.items())
        if name not in IGNORED_INTERFACES
    ][:INTERFACES_MAX]


def parse_tcp_counters(snmp: str | None) -> dict[str, int]:
    if snmp is None:
        return {}
    tcp_lines = [line.split() for line in snmp.splitlines() if line.startswith("Tcp:")]
    if len(tcp_lines) < 2:
        return {}
    names, values = tcp_lines[0][1:], tcp_lines[1][1:]
    return {name: int(value) for name, value in zip(names, values, strict=False) if value.isdigit()}


def read_optional_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def read_optional_int(path: Path) -> int | None:
    text = read_optional_text(path)
    if text is None or not text.strip().isdigit():
        return None
    return int(text)
