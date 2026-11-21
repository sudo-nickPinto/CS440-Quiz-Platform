from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.quiz_edit_notifications import run_quiz_edit_with_notifications
from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.question_bank import (
    BankScope, BankSelection, ClassBankDownload, ClassBankQuizzesResponse, CsvImportRequest, CsvImportResponse,
    CsvBankSaveRequest, CsvBankSaveResponse, CsvPreviewRequest,
    CsvPreviewResponse, DuplicateQuizResponse, QuestionBankPage,
)
from app.schemas.quiz import QuizResponse
from app.services.question_bank import (
    add_from_bank, download_class_csv, duplicate_quiz, export_csv, import_csv,
    list_bank, list_class_bank_items, list_class_bank_quizzes, preview_csv,
    save_csv_to_bank,
)

router = APIRouter(prefix="/classes/{class_id}", tags=["question bank"])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/question-bank", response_model=QuestionBankPage)
def list_question_bank(class_id: int, scope: BankScope = BankScope.CLASS,
                       search: str = Query(default="", max_length=200), page: Page = 1,
                       page_size: PageSize = 25, db: Session = Depends(get_db),
                       account: CurrentAccount = Depends(get_active_account)):
    return list_bank(db, account, class_id, scope=scope, search=search,
                     page=page, page_size=page_size)


@router.post("/question-bank/csv/preview", response_model=CsvPreviewResponse)
def preview_question_csv(class_id: int, payload: CsvPreviewRequest,
                         db: Session = Depends(get_db),
                         account: CurrentAccount = Depends(get_active_account)):
    # Membership is checked before parsing to keep this class-scoped endpoint private.
    from app.services.quizzes import _require_active_membership
    _require_active_membership(db, account, class_id)
    return preview_csv(payload.csv_text)


@router.post("/question-bank/csv", response_model=CsvBankSaveResponse,
             status_code=status.HTTP_201_CREATED)
def save_question_csv_to_bank(
    class_id: int,
    payload: CsvBankSaveRequest,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
):
    return save_csv_to_bank(db, account, class_id, payload)


@router.get("/question-bank/export.csv")
def export_question_csv(class_id: int, scope: BankScope = BankScope.CLASS,
                        ids: list[int] | None = Query(default=None),
                        db: Session = Depends(get_db),
                        account: CurrentAccount = Depends(get_active_account)):
    content = export_csv(db, account, class_id, scope, ids)
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=question-bank.csv"})


@router.post("/quizzes/{quiz_id}/questions/from-bank", response_model=QuizResponse)
def add_bank_questions(
    class_id: int,
    quiz_id: int,
    payload: BankSelection,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
):
    return run_quiz_edit_with_notifications(
        db, request.app.state.notification_hub, background_tasks,
        add_from_bank, account, class_id, quiz_id, payload.bank_question_ids,
    )


@router.post("/quizzes/{quiz_id}/questions/csv", response_model=CsvImportResponse)
def import_question_csv(
    class_id: int,
    quiz_id: int,
    payload: CsvImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
):
    return run_quiz_edit_with_notifications(
        db, request.app.state.notification_hub, background_tasks,
        import_csv, account, class_id, quiz_id, payload,
    )


@router.post("/quizzes/{quiz_id}/duplicate", response_model=DuplicateQuizResponse,
             status_code=status.HTTP_201_CREATED)
def duplicate_class_quiz(class_id: int, quiz_id: int, db: Session = Depends(get_db),
                         account: CurrentAccount = Depends(get_active_account)):
    return DuplicateQuizResponse(quiz=duplicate_quiz(db, account, class_id, quiz_id))


# The class dashboard's question bank (organizers): download this class's
# questions as CSV.


@router.get("/question-bank/quizzes", response_model=ClassBankQuizzesResponse)
def list_class_bank_quizzes_route(class_id: int, db: Session = Depends(get_db),
                                  account: CurrentAccount = Depends(get_active_account)):
    return list_class_bank_quizzes(db, account, class_id)


@router.get("/question-bank/items", response_model=QuestionBankPage)
def list_class_bank_items_route(class_id: int, page: Page = 1, page_size: PageSize = 25,
                                db: Session = Depends(get_db),
                                account: CurrentAccount = Depends(get_active_account)):
    return list_class_bank_items(db, account, class_id, page=page, page_size=page_size)


@router.post("/question-bank/download.csv")
def download_class_bank_csv(class_id: int, payload: ClassBankDownload,
                            db: Session = Depends(get_db),
                            account: CurrentAccount = Depends(get_active_account)):
    content = download_class_csv(db, account, class_id, payload.bank_question_ids)
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=question-bank.csv"})
