import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import Response as HTTPResponse
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.models.quiz_submission import SubmissionStatus
from app.schemas.class_dashboard import (
    ApprovedQuizSort,
    ClassApprovedQuizPage,
    ClassSubmissionPage,
    ClassSubmissionPreview,
    SubmissionSort,
    ClassDashboardResponse,
    ClassQuizPage,
    ClassSessionPage,
    ClassStudentPage,
    QuizSort,
    SessionSort,
    SortOrder,
    StudentSort,
)
from app.services.class_approvals import (
    list_class_approved_quizzes,
    get_class_submission_preview,
    list_class_submissions,
)
from app.services.class_dashboard import (
    export_class_grades,
    get_class_dashboard,
    list_class_quizzes,
    list_class_sessions,
    list_class_students,
)

router = APIRouter(prefix="/classes/{class_id}", tags=["class dashboard"])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/dashboard", response_model=ClassDashboardResponse)
def class_dashboard_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassDashboardResponse:
    return get_class_dashboard(db, account, class_id)


# The class's own quizzes live at /quizzes (class_quizzes.py); this is the
# history of quizzes that were played in the class.
@router.get("/presented-quizzes", response_model=ClassQuizPage)
def class_quizzes_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    sort: QuizSort = QuizSort.PRESENTED_AT,
    order: SortOrder = SortOrder.DESC,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassQuizPage:
    return list_class_quizzes(
        db, account, class_id, page=page, page_size=page_size, sort=sort, order=order
    )


@router.get("/sessions", response_model=ClassSessionPage)
def class_sessions_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    sort: SessionSort = SessionSort.STARTED_AT,
    order: SortOrder = SortOrder.DESC,
    q: Annotated[str | None, Query(max_length=200)] = None,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassSessionPage:
    return list_class_sessions(
        db, account, class_id, page=page, page_size=page_size, sort=sort, order=order, q=q
    )


@router.get("/students", response_model=ClassStudentPage)
def class_students_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    sort: StudentSort = StudentSort.NAME,
    order: SortOrder = SortOrder.ASC,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassStudentPage:
    return list_class_students(
        db, account, class_id, page=page, page_size=page_size, sort=sort, order=order
    )


# Dashboard views of the Task 4 approval queue: paged, sorted, and with
# names and version details filled in. /quiz-submissions and
# /approved-quizzes remain the endpoints that change or check approvals.
@router.get("/dashboard/submissions", response_model=ClassSubmissionPage)
def class_submissions_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    sort: SubmissionSort = SubmissionSort.SUBMITTED_AT,
    order: SortOrder = SortOrder.DESC,
    status: SubmissionStatus | None = None,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassSubmissionPage:
    return list_class_submissions(
        db,
        account,
        class_id,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        status=status,
    )


@router.get(
    "/dashboard/submissions/{submission_id}/preview",
    response_model=ClassSubmissionPreview,
)
def class_submission_preview_route(
    class_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassSubmissionPreview:
    return get_class_submission_preview(db, account, class_id, submission_id)


@router.get("/dashboard/approved-quizzes", response_model=ClassApprovedQuizPage)
def class_approved_quizzes_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    sort: ApprovedQuizSort = ApprovedQuizSort.APPROVED_AT,
    order: SortOrder = SortOrder.DESC,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassApprovedQuizPage:
    return list_class_approved_quizzes(
        db, account, class_id, page=page, page_size=page_size, sort=sort, order=order
    )


@router.get("/grades/export.csv")
def class_grades_export_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> HTTPResponse:
    content, class_name = export_class_grades(db, account, class_id)
    # Keep the filename to safe ASCII so the header can't be broken.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", class_name).strip("-").lower() or "class"
    return HTTPResponse(
        content="\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-grades.csv"',
            "Cache-Control": "no-store",
        },
    )
