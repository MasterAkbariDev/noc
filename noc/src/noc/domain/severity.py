from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @classmethod
    def parse(cls, value: str | None) -> "Severity":
        try:
            return cls((value or "").lower())
        except ValueError:
            return cls.WARNING

    @classmethod
    def highest(cls, *values: "Severity") -> "Severity":
        return max(values, key=lambda severity: severity.rank, default=cls.INFO)


_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
