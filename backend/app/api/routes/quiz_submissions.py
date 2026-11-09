from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
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
def create_quiz_submission_route(
    class_id: int,
    payload: QuizSubmissionCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizSubmissionResponse:
    return create_quiz_submission(db, account, class_id, payload)


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
def decide_quiz_submission_route(
    class_id: int,
    submission_id: int,
    payload: QuizSubmissionDecision,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizSubmissionResponse:
    return decide_quiz_submission(
        db, account, class_id, submission_id, payload
    )


@router.delete(
    "/quiz-submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def withdraw_quiz_submission_route(
    class_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    withdraw_quiz_submission(db, account, class_id, submission_id)
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
