from fastapi import APIRouter, Depends

from app.auth import get_account_record
from app.models.account import effective_role

router = APIRouter(tags=["accounts"])


@router.get("/me")
def me(account: dict = Depends(get_account_record)) -> dict:
    return {
        "account_id": account["account_id"],
        "email": account["email"],
        "display_name": account["display_name"],
        "role": effective_role(account["account_type"]),
        "is_active": bool(account["is_active"]),
    }
