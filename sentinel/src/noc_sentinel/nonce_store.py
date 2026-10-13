import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path


class NonceStore:
    def __init__(self, database: Path | str, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(database), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, seen_at REAL NOT NULL)"
        )
        self._db.commit()

    def remember(self, nonce: str, seen_at: datetime) -> bool:
        cutoff = (seen_at - self._ttl).timestamp()
        with self._lock:
            self._db.execute("DELETE FROM nonces WHERE seen_at < ?", (cutoff,))
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO nonces (nonce, seen_at) VALUES (?, ?)",
                (nonce, seen_at.timestamp()),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def close(self) -> None:
        with self._lock:
            self._db.close()
