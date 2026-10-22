from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.class_dashboard import (
    ClassDashboardResponse,
    ClassQuizPage,
    ClassSessionPage,
    ClassStudentPage,
    QuizSort,
    SessionSort,
    SortOrder,
    StudentSort,
)
from app.services.class_dashboard import (
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


@router.get("/quizzes", response_model=ClassQuizPage)
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
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassSessionPage:
    return list_class_sessions(
        db, account, class_id, page=page, page_size=page_size, sort=sort, order=order
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
