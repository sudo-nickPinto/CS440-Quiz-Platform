from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.response import ResponseReceipt, ResponseSubmit
from app.services.responses import submit_response

router = APIRouter(prefix="/sessions", tags=["responses"])


@router.post(
    "/{session_id}/questions/{session_question_id}/responses",
    response_model=ResponseReceipt,
    status_code=status.HTTP_201_CREATED,
)
def submit_response_route(
    payload: ResponseSubmit,
    session_id: int = Path(gt=0),
    session_question_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ResponseReceipt:
    return submit_response(
        db,
        account,
        session_id,
        session_question_id,
        payload,
    )
