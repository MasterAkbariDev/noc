import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from noc_shared.actions import ActionResult


@dataclass(frozen=True)
class StoredAction:
    action_hash: str
    result: ActionResult


def timestamp_key(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


class ActionStore:
    def __init__(self, database: Path | str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(database), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS actions ("
            "action_id TEXT PRIMARY KEY, "
            "action_hash TEXT NOT NULL, "
            "resource_id TEXT NOT NULL, "
            "status TEXT NOT NULL, "
            "result_json TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self._db.commit()

    def get(self, action_id: UUID) -> StoredAction | None:
        with self._lock:
            row = self._db.execute(
                "SELECT action_hash, result_json FROM actions WHERE action_id = ?",
                (str(action_id),),
            ).fetchone()
        if row is None:
            return None
        return StoredAction(action_hash=row[0], result=ActionResult.model_validate_json(row[1]))

    def insert_executing(self, action_hash: str, result: ActionResult) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO actions (action_id, action_hash, resource_id, status, result_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(result.action_id),
                    action_hash,
                    result.resource_id,
                    result.status,
                    result.model_dump_json(),
                    timestamp_key(result.started_at),
                ),
            )
            self._db.commit()

    def finish(self, result: ActionResult) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE actions SET status = ?, result_json = ? WHERE action_id = ?",
                (result.status, result.model_dump_json(), str(result.action_id)),
            )
            self._db.commit()

    def count_since(self, resource_id: str, since: datetime) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) FROM actions WHERE resource_id = ? AND created_at >= ?",
                (resource_id, timestamp_key(since)),
            ).fetchone()
        return int(row[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()
