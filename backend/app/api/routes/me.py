from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.accounts import update_profile
from app.auth import get_account_record
from app.database import get_db
from app.errors import APIError
from app.models.account import effective_role

router = APIRouter(tags=["accounts"])


class ProfileUpdate(BaseModel):
    """The whole profile; the setup screen and Edit profile always send all three."""

    model_config = ConfigDict(extra="forbid")

    # Generous limits here only stop huge bodies; clean_name enforces 50 after trimming.
    first_name: str = Field(max_length=200)
    last_name: str = Field(max_length=200)
    # Required but nullable: null means "no avatar, show initials".
    avatar_key: str | None = Field(max_length=32)


def _me_body(account: dict) -> dict:
    return {
        "account_id": account["account_id"],
        "email": account["email"],
        "display_name": account["display_name"],
        "first_name": account["first_name"],
        "last_name": account["last_name"],
        "avatar_key": account["avatar_key"],
        # The app shows the profile setup screen until both names are saved.
        "profile_complete": bool(account["first_name"] and account["last_name"]),
        "role": effective_role(account["account_type"]),
        "is_active": bool(account["is_active"]),
    }


@router.get("/me")
def me(account: dict = Depends(get_account_record)) -> dict:
    return _me_body(account)


@router.patch("/me")
def update_me(
    body: ProfileUpdate,
    account: dict = Depends(get_account_record),
    db: Session = Depends(get_db),
) -> dict:
    if not account["is_active"]:
        raise APIError(403, "inactive_account", "This account is inactive.")
    return _me_body(
        update_profile(
            db,
            account["account_id"],
            body.first_name,
            body.last_name,
            body.avatar_key,
        )
    )
