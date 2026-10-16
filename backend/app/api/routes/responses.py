from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request, status
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
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: int = Path(gt=0),
    session_question_id: int = Path(gt=0),
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ResponseReceipt:
    receipt = submit_response(
        db,
        account,
        session_id,
        session_question_id,
        payload,
    )
    # Same after-answer hook as the live socket, so REST answers still close
    # the question and notify the host (LIVE_PROTOCOL.md §4).
    background_tasks.add_task(
        request.app.state.live_hub.after_answer, session_id, session_question_id
    )
    return receipt
