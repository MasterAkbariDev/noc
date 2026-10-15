import os
import re
import secrets
from pathlib import Path
from typing import Final

NAME_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
FILE_SUFFIX: Final = ".secret"
FILE_MODE: Final = 0o600
DIRECTORY_MODE: Final = 0o700


class SecretStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def is_persistent(self) -> bool:
        return os.path.ismount(self._directory)

    def path_for(self, name: str) -> Path:
        if NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(f"invalid secret name {name!r}")
        return self._directory / f"{name}{FILE_SUFFIX}"

    def write(self, name: str, value: str) -> None:
        target = self.path_for(name)
        self._directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        temporary = self._directory / f".{name}.{secrets.token_hex(6)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def read(self, name: str) -> str | None:
        try:
            return self.path_for(name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def delete(self, name: str) -> None:
        self.path_for(name).unlink(missing_ok=True)
