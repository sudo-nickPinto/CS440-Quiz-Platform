from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.models.quiz_submission import SubmissionStatus
from app.notifications.events import notify_submission_changed
from app.schemas.quiz_submission import (
    ApprovedQuizResponse,
    QuizSubmissionCreate,
    QuizSubmissionDecision,
    QuizSubmissionResponse,
)
from app.services.quiz_submissions import (
    create_quiz_submission,
    decide_quiz_submission,
    list_approved_quizzes,
    list_quiz_submissions,
    withdraw_quiz_submission,
)

router = APIRouter(prefix="/classes/{class_id}", tags=["quiz submissions"])


@router.post(
    "/quiz-submissions",
    response_model=QuizSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quiz_submission_route(
    class_id: int,
    payload: QuizSubmissionCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    account: CurrentAccount = Depends(get_active_account),
) -> QuizSubmissionResponse:
    hub = request.app.state.notification_hub
    result = await hub.run_db(create_quiz_submission, account, class_id, payload)
    # Runs after the response is sent; failures are logged, never raised.
    background_tasks.add_task(
        notify_submission_changed,
        hub,
        submission_id=result.submission_id,
        action="submitted",
        actor_account_id=account.account_id,
    )
    return result


@router.get(
    "/quiz-submissions",
    response_model=list[QuizSubmissionResponse],
)
def list_quiz_submissions_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[QuizSubmissionResponse]:
    return list_quiz_submissions(db, account, class_id)


@router.patch(
    "/quiz-submissions/{submission_id}",
    response_model=QuizSubmissionResponse,
)
async def decide_quiz_submission_route(
    class_id: int,
    submission_id: int,
    payload: QuizSubmissionDecision,
    request: Request,
    background_tasks: BackgroundTasks,
    account: CurrentAccount = Depends(get_active_account),
) -> QuizSubmissionResponse:
    hub = request.app.state.notification_hub
    result = await hub.run_db(
        decide_quiz_submission, account, class_id, submission_id, payload
    )
    background_tasks.add_task(
        notify_submission_changed,
        hub,
        submission_id=result.submission_id,
        action=(
            "approved" if result.status == SubmissionStatus.APPROVED else "rejected"
        ),
        actor_account_id=account.account_id,
    )
    return result


@router.delete(
    "/quiz-submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_quiz_submission_route(
    class_id: int,
    submission_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    hub = request.app.state.notification_hub
    await hub.run_db(withdraw_quiz_submission, account, class_id, submission_id)
    background_tasks.add_task(
        notify_submission_changed,
        hub,
        submission_id=submission_id,
        action="withdrawn",
        actor_account_id=account.account_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/approved-quizzes",
    response_model=list[ApprovedQuizResponse],
)
def list_approved_quizzes_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[ApprovedQuizResponse]:
    return list_approved_quizzes(db, account, class_id)
