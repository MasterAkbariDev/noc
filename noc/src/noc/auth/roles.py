from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


ROLE_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}


def role_allows(have: Role, need: Role) -> bool:
    return ROLE_RANK[have] >= ROLE_RANK[need]
