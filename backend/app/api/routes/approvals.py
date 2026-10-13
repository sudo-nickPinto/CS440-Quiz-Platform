from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.errors import APIError

# Approving accounts in the app replaces Auth0's verification email.
# For testing, any active account can approve; require `account.is_admin`
# once this moves into the admin area.
router = APIRouter(prefix="/accounts", tags=["approvals"])


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT account_id, email, display_name, created_at FROM account "
            "WHERE is_active = FALSE ORDER BY created_at, account_id"
        )
    ).mappings()
    return [dict(row) for row in rows]


@router.post("/{account_id}/approve")
def approve_account(
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    result = db.execute(
        text("UPDATE account SET is_active = TRUE WHERE account_id = :id AND is_active = FALSE"),
        {"id": account_id},
    )
    if result.rowcount == 0:
        raise APIError(404, "not_pending", "That account is not waiting for approval.")
    db.commit()
    return {"account_id": account_id, "is_active": True}


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def reject_account(
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> None:
    # Only pending accounts can be rejected; their logins are deleted with them.
    try:
        result = db.execute(
            text("DELETE FROM account WHERE account_id = :id AND is_active = FALSE"),
            {"id": account_id},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "account_in_use", "That account owns data and cannot be deleted.") from exc
    if result.rowcount == 0:
        raise APIError(404, "not_pending", "That account is not waiting for approval.")
