import os
import re
import time
from contextlib import suppress
from datetime import UTC, datetime
from statistics import mean
from typing import Protocol

import psutil

from noc_shared.tools import (
    CpuUsage,
    DiskUsage,
    MemoryUsage,
    MountUsage,
    ProcessInfo,
    ProcessSort,
)

CPU_SAMPLE_SECONDS = 0.5
CMDLINE_MAX_CHARS = 200
IGNORED_FILESYSTEMS = frozenset({"tmpfs", "devtmpfs", "overlay", "squashfs"})
PROC_ROOT = "/proc"
CGROUP_UNIT = re.compile(r"/([A-Za-z0-9@._-]{1,128}\.service)(?:/|$)")


class HostReader(Protocol):
    def cpu(self) -> CpuUsage: ...

    def memory(self) -> MemoryUsage: ...

    def disks(self) -> DiskUsage: ...

    def processes(self, sort_by: ProcessSort, limit: int) -> list[ProcessInfo]: ...


class PsutilHostReader:
    def cpu(self) -> CpuUsage:
        cores = psutil.cpu_times_percent(interval=CPU_SAMPLE_SECONDS, percpu=True)
        load_1m, load_5m, load_15m = os.getloadavg()
        return CpuUsage(
            percent=round(mean(busy_percent(core.idle) for core in cores), 1),
            per_core_percent=[round(busy_percent(core.idle), 1) for core in cores],
            steal_percent=round(mean(getattr(core, "steal", 0.0) for core in cores), 1),
            iowait_percent=round(mean(getattr(core, "iowait", 0.0) for core in cores), 1),
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
        )

    def memory(self) -> MemoryUsage:
        virtual = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return MemoryUsage(
            total_bytes=virtual.total,
            used_bytes=virtual.used,
            available_bytes=virtual.available,
            cached_bytes=getattr(virtual, "cached", None),
            swap_total_bytes=swap.total,
            swap_used_bytes=swap.used,
        )

    def disks(self) -> DiskUsage:
        return DiskUsage(mounts=real_mounts())

    def processes(self, sort_by: ProcessSort, limit: int) -> list[ProcessInfo]:
        handles = list(psutil.process_iter())
        for handle in handles:
            prime_cpu_counter(handle)
        time.sleep(CPU_SAMPLE_SECONDS)
        snapshots = [
            snapshot for handle in handles if (snapshot := read_process(handle)) is not None
        ]
        return sorted(snapshots, key=lambda item: sort_value(item, sort_by), reverse=True)[:limit]


def busy_percent(idle: float) -> float:
    return 100.0 - idle


def real_mounts() -> list[MountUsage]:
    mounts: list[MountUsage] = []
    for partition in psutil.disk_partitions(all=False):
        if partition.fstype in IGNORED_FILESYSTEMS:
            continue
        with suppress(OSError):
            mounts.append(mount_usage(partition.device, partition.mountpoint, partition.fstype))
    return mounts


def mount_usage(device: str, mountpoint: str, fstype: str) -> MountUsage:
    usage = psutil.disk_usage(mountpoint)
    stats = os.statvfs(mountpoint)
    return MountUsage(
        mountpoint=mountpoint,
        device=device,
        fstype=fstype,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        percent=round(usage.percent, 1),
        inodes_total=stats.f_files,
        inodes_used=stats.f_files - stats.f_ffree,
    )


def prime_cpu_counter(handle: psutil.Process) -> None:
    with suppress(psutil.Error):
        handle.cpu_percent(None)


def read_process(handle: psutil.Process) -> ProcessInfo | None:
    try:
        with handle.oneshot():
            return ProcessInfo(
                pid=handle.pid,
                name=handle.name(),
                user=handle.username(),
                cpu_percent=round(handle.cpu_percent(None), 1),
                rss_bytes=handle.memory_info().rss,
                started_at=datetime.fromtimestamp(handle.create_time(), UTC).isoformat(),
                cmdline=" ".join(handle.cmdline())[:CMDLINE_MAX_CHARS],
                unit=process_unit(handle.pid),
            )
    except psutil.Error:
        return None


def unit_from_cgroup(cgroup_text: str) -> str | None:
    units = CGROUP_UNIT.findall(cgroup_text)
    return units[-1] if units else None


def process_unit(pid: int, proc_root: str = PROC_ROOT) -> str | None:
    try:
        with open(f"{proc_root}/{pid}/cgroup", encoding="utf-8") as handle:
            return unit_from_cgroup(handle.read(4096))
    except OSError:
        return None


def sort_value(process: ProcessInfo, sort_by: ProcessSort) -> float:
    return process.cpu_percent if sort_by == "cpu" else float(process.rss_bytes)
