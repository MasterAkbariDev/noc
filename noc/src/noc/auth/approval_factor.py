import uuid
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.auth.totp import matching_step
from noc.auth.users import claim_totp_step, subject_for
from noc.db.base import utc_now
from noc.db.models import User

CODE_REQUIRED: Final = "authentication code required"
CODE_INVALID: Final = "invalid authentication code"
NEEDS_PERSON: Final = "production approvals need a signed-in person, not an API token"
NEEDS_ENROLMENT: Final = (
    "turn on two-factor authentication in Settings before approving production actions"
)


class SecondFactorRefused(Exception):
    pass


async def confirm_second_factor(
    session: AsyncSession, user_id: uuid.UUID | None, code: str | None, subject: str
) -> None:
    if user_id is None:
        raise SecondFactorRefused(NEEDS_PERSON)
    user = await session.get(User, user_id)
    if user is None or not user.totp_enabled or user.totp_secret is None:
        raise SecondFactorRefused(NEEDS_ENROLMENT)
    if not code:
        raise SecondFactorRefused(CODE_REQUIRED)
    step = matching_step(user.totp_secret, code, utc_now(), user.totp_last_step)
    if step is None or not await claim_totp_step(session, user.id, step):
        await append_audit(
            session, user.username, "approval_code_refused", subject_for(user.username), {}
        )
        await session.commit()
        raise SecondFactorRefused(CODE_INVALID)
    await append_audit(session, user.username, "approval_reauthenticated", subject, {})
    await session.commit()
