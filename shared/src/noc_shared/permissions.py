from enum import IntEnum


class PermissionClass(IntEnum):
    READ_ONLY = 0
    SAFE_ACTION = 1
    REQUIRES_APPROVAL = 2
    BLOCKED = 3

    @classmethod
    def strictest(cls, *classes: "PermissionClass") -> "PermissionClass":
        return max(classes, default=cls.READ_ONLY)
