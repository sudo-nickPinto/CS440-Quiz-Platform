from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from math import ceil

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.classes import ClassRole
from app.models.quiz import (
    AnswerChoice,
    Question,
    QuestionBankItem,
    Quiz,
    QuizCollaborator,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from app.schemas.pagination import PageInfo
from app.schemas.question_bank import (
    BankScope,
    CsvBankSaveRequest,
    CsvBankSaveResponse,
    CsvImportRequest,
    CsvImportResponse,
    CsvPreviewResponse,
    CsvPreviewRow,
    QuestionBankItemResponse,
    QuestionBankPage,
)
from app.schemas.quiz import AnswerChoiceCreate, QuestionCreate

CSV_COLUMNS = [
    "question_text", "explanation", "choice_a", "choice_b", "choice_c",
    "choice_d", "correct_choices",
]
MAX_CSV_ROWS = 500


def _choice_data(question: Question) -> list[dict]:
    return [
        {"choice_text": choice.choice_text, "is_correct": choice.is_correct}
        for choice in sorted(question.choices, key=lambda item: item.choice_order)
    ]


def snapshot_question(
    db: Session, question: Question, *, owner_id: int, class_id: int | None,
    quiz_id: int | None, current: bool = True,
) -> QuestionBankItem:
    item = None
    if question.bank_question_id:
        item = db.get(QuestionBankItem, question.bank_question_id)
    if item is None and question.question_id:
        item = db.scalar(select(QuestionBankItem).where(
            QuestionBankItem.source_question_id == question.question_id
        ))
    if item is None:
        item = QuestionBankItem(owner_id=owner_id)
        db.add(item)
    item.source_class_id = class_id
    item.source_quiz_id = quiz_id
    item.source_question_id = question.question_id
    item.is_current = current
    item.question_type = question.question_type
    item.question_text = question.question_text
    item.explanation = question.explanation
    item.choices_json = _choice_data(question)
    db.flush()
    question.bank_question_id = item.bank_question_id
    return item


def _collaborator_quiz_ids(account: CurrentAccount):
    return select(QuizCollaborator.quiz_id).where(
        QuizCollaborator.account_id == account.account_id,
        QuizCollaborator.revoked_at.is_(None),
    )


def _ensure_legacy_snapshots(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    is_organizer: bool,
) -> None:
    conditions = [
        Quiz.author_id == account.account_id,
        Quiz.quiz_id.in_(_collaborator_quiz_ids(account)),
    ]
    if is_organizer:
        conditions.append(
            (Quiz.class_id == class_id) & (Quiz.status == QuizStatus.PUBLISHED)
        )
    rows = db.execute(
        select(Question, Quiz.author_id, Quiz.class_id, Quiz.quiz_id)
        .join(QuizVersion, QuizVersion.quiz_version_id == Question.quiz_version_id)
        .join(Quiz, Quiz.quiz_id == QuizVersion.quiz_id)
        .where(or_(*conditions), Question.bank_question_id.is_(None))
        .options(selectinload(Question.choices))
    ).all()
    for question, owner_id, source_class_id, quiz_id in rows:
        snapshot_question(db, question, owner_id=owner_id, class_id=source_class_id,
                          quiz_id=quiz_id)
    if rows:
        db.commit()


def _visible_condition(
    account: CurrentAccount,
    class_id: int,
    scope: BankScope,
    *,
    is_organizer: bool,
):
    mine = QuestionBankItem.owner_id == account.account_id
    collaborated = QuestionBankItem.source_quiz_id.in_(
        _collaborator_quiz_ids(account)
    )
    if scope == BankScope.MINE:
        return or_(mine, collaborated)
    conditions = [mine, collaborated]
    if is_organizer:
        published_class_quiz_ids = select(Quiz.quiz_id).where(
            Quiz.class_id == class_id,
            Quiz.status == QuizStatus.PUBLISHED,
        )
        conditions.append(
            QuestionBankItem.source_quiz_id.in_(published_class_quiz_ids)
        )
    return or_(*conditions)


def _response(item: QuestionBankItem) -> QuestionBankItemResponse:
    return QuestionBankItemResponse(
        bank_question_id=item.bank_question_id, owner_id=item.owner_id,
        source_class_id=item.source_class_id, question_type=item.question_type,
        question_text=item.question_text, explanation=item.explanation,
        choices=[AnswerChoiceCreate.model_validate(choice) for choice in item.choices_json],
        updated_at=item.updated_at,
    )


def list_bank(db: Session, account: CurrentAccount, class_id: int, *, scope: BankScope,
              search: str, page: int, page_size: int) -> QuestionBankPage:
    from app.services.quizzes import _require_active_membership
    membership = _require_active_membership(db, account, class_id)
    is_organizer = membership.role == ClassRole.ORGANIZER
    _ensure_legacy_snapshots(
        db, account, class_id, is_organizer=is_organizer
    )
    condition = _visible_condition(
        account, class_id, scope, is_organizer=is_organizer
    )
    if search.strip():
        condition = condition & QuestionBankItem.question_text.ilike(f"%{search.strip()}%")
    condition = condition & QuestionBankItem.is_current.is_(True)
    total = db.scalar(select(func.count()).select_from(QuestionBankItem).where(condition)) or 0
    items = list(db.scalars(select(QuestionBankItem).where(condition)
        .order_by(QuestionBankItem.updated_at.desc(), QuestionBankItem.bank_question_id.desc())
        .limit(page_size).offset((page - 1) * page_size)))
    return QuestionBankPage(items=[_response(item) for item in items], pagination=PageInfo(
        page=page, page_size=page_size, total_items=total,
        total_pages=ceil(total / page_size) if total else 0,
    ))


def _destination_time(version: QuizVersion) -> int:
    """Use the destination quiz's effective default, matching the editor's rule."""
    counts: dict[int, int] = {}
    selected = 20
    highest = 0
    for question in sorted(version.questions, key=lambda value: value.question_order):
        seconds = question.time_limit_seconds
        counts[seconds] = counts.get(seconds, 0) + 1
        if counts[seconds] > highest:
            selected = seconds
            highest = counts[seconds]
    return selected


def _question_from_item(item: QuestionBankItem, order: int, *, time_limit_seconds: int) -> Question:
    return Question(question_order=order, question_type=item.question_type,
        question_text=item.question_text, explanation=item.explanation,
        time_limit_seconds=time_limit_seconds, base_points=1000,
        choices=[AnswerChoice(choice_order=index, choice_text=choice["choice_text"],
            is_correct=choice["is_correct"]) for index, choice in enumerate(item.choices_json, 1)])


def _copy_question(question: Question, order: int) -> Question:
    return Question(
        question_order=order,
        question_type=question.question_type,
        question_text=question.question_text,
        explanation=question.explanation,
        time_limit_seconds=question.time_limit_seconds,
        base_points=question.base_points,
        choices=[
            AnswerChoice(
                choice_order=choice.choice_order,
                choice_text=choice.choice_text,
                is_correct=choice.is_correct,
            )
            for choice in sorted(question.choices, key=lambda item: item.choice_order)
        ],
    )


def add_from_bank(db: Session, account: CurrentAccount, class_id: int, quiz_id: int,
                  bank_ids: list[int]):
    from app.services.quizzes import (
        _latest_editor_version, _load_readable_quiz, _require_active_membership,
        _require_quiz_editor, _to_response,
    )
    membership = _require_active_membership(db, account, class_id)
    quiz = _load_readable_quiz(db, account, quiz_id)
    _require_quiz_editor(db, account, quiz)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    if quiz.status != QuizStatus.DRAFT:
        raise APIError(409, "quiz_not_editable", "Only draft quizzes can receive questions.")
    visible = _visible_condition(
        account,
        class_id,
        BankScope.CLASS,
        is_organizer=membership.role == ClassRole.ORGANIZER,
    )
    items = list(db.scalars(select(QuestionBankItem).where(
        QuestionBankItem.bank_question_id.in_(bank_ids), visible,
        QuestionBankItem.is_current.is_(True))))
    by_id = {item.bank_question_id: item for item in items}
    if set(by_id) != set(bank_ids):
        raise APIError(404, "bank_question_not_found", "A selected question is unavailable.")
    version = _latest_editor_version(quiz)
    destination_time = _destination_time(version)
    order = max((q.question_order for q in version.questions), default=0)
    for bank_id in bank_ids:
        order += 1
        question = _question_from_item(
            by_id[bank_id], order, time_limit_seconds=destination_time
        )
        version.questions.append(question)
        db.flush()
        snapshot_question(db, question, owner_id=quiz.author_id, class_id=class_id, quiz_id=quiz_id)
    quiz.revision += 1
    quiz.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    db.expire_all()
    return _to_response(db, account, _load_readable_quiz(db, account, quiz_id))


def duplicate_quiz(db: Session, account: CurrentAccount, class_id: int, quiz_id: int):
    from app.services.quizzes import (
        _latest_editor_version, _load_readable_quiz, _require_active_membership,
        _to_response,
    )
    _require_active_membership(db, account, class_id)
    source = _load_readable_quiz(db, account, quiz_id)
    if source.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    source_version = _latest_editor_version(source)
    copied = Quiz(author_id=account.account_id, class_id=class_id, status=QuizStatus.DRAFT,
        visibility=QuizVisibility.PRIVATE, revision=1, versions=[QuizVersion(
            version_number=1, title=f"Copy of {source_version.title}"[:200],
            description=source_version.description, questions=[
                _copy_question(question, question.question_order)
                for question in source_version.questions
            ])])
    db.add(copied); db.flush()
    for question in copied.versions[0].questions:
        snapshot_question(db, question, owner_id=account.account_id, class_id=class_id,
                          quiz_id=copied.quiz_id)
    db.commit(); db.expire_all()
    return _to_response(db, account, _load_readable_quiz(db, account, copied.quiz_id))


def preview_csv(text: str) -> CsvPreviewResponse:
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != CSV_COLUMNS:
            raise APIError(422, "csv_headers_invalid", "CSV headers must exactly match the template.",
                details={"expected": CSV_COLUMNS, "received": reader.fieldnames or []})
        rows = []
        for number, raw in enumerate(reader, 2):
            if len(rows) >= MAX_CSV_ROWS:
                raise APIError(
                    422,
                    "csv_too_many_rows",
                    f"CSV files may contain at most {MAX_CSV_ROWS} question rows.",
                )
            errors = []
            try:
                choices = []
                for key in "abcd":
                    value = (raw[f"choice_{key}"] or "").strip()
                    if value:
                        choices.append((key.upper(), value))
                correct = {part.strip().upper() for part in (raw["correct_choices"] or "").split("|") if part.strip()}
                unknown = correct - {letter for letter, _ in choices}
                if unknown: errors.append(f"Unknown correct choice(s): {', '.join(sorted(unknown))}.")
                payload = QuestionCreate(question_text=raw["question_text"],
                    explanation=raw["explanation"] or None,
                    choices=[AnswerChoiceCreate(choice_text=value, is_correct=letter in correct)
                             for letter, value in choices])
                rows.append(CsvPreviewRow(row_number=number, valid=not errors,
                    question=payload if not errors else None, errors=errors))
            except (ValueError, ValidationError) as exc:
                rows.append(CsvPreviewRow(row_number=number, valid=False, errors=[str(exc)]))
    except csv.Error as exc:
        raise APIError(422, "csv_invalid", "The CSV could not be parsed.") from exc
    return CsvPreviewResponse(rows=rows, valid_count=sum(r.valid for r in rows),
        invalid_count=sum(not r.valid for r in rows))


def import_csv(db: Session, account: CurrentAccount, class_id: int, quiz_id: int,
               payload: CsvImportRequest) -> CsvImportResponse:
    from app.services.quizzes import (
        _latest_editor_version, _load_readable_quiz, _require_active_membership,
        _require_quiz_editor, _to_response,
    )
    # Selected rows enter the quiz and are automatically banked.
    quiz = _load_readable_quiz(db, account, quiz_id)
    _require_active_membership(db, account, class_id); _require_quiz_editor(db, account, quiz)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    if quiz.status != QuizStatus.DRAFT:
        raise APIError(409, "quiz_not_editable", "Only draft quizzes can receive questions.")
    version = _latest_editor_version(quiz)
    destination_time = _destination_time(version)
    order = max((q.question_order for q in version.questions), default=0)
    for row in payload.rows:
        order += 1
        question = Question(question_order=order, question_text=row.question.question_text,
            explanation=row.question.explanation, time_limit_seconds=destination_time,
            base_points=1000, choices=[AnswerChoice(choice_order=i,
                choice_text=c.choice_text, is_correct=c.is_correct) for i, c in enumerate(row.question.choices, 1)])
        version.questions.append(question); db.flush()
        snapshot_question(db, question, owner_id=quiz.author_id, class_id=class_id, quiz_id=quiz_id)
    saved_only = 0
    if payload.save_unselected_to_bank:
        for row in payload.bank_only_rows:
            db.add(QuestionBankItem(owner_id=account.account_id, source_class_id=class_id,
                is_current=True, question_text=row.question.question_text,
                explanation=row.question.explanation,
                choices_json=[c.model_dump() for c in row.question.choices]))
            saved_only += 1
    quiz.revision += 1; quiz.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit(); db.expire_all()
    return CsvImportResponse(quiz=_to_response(db, account, _load_readable_quiz(db, account, quiz_id)),
        added_to_quiz=len(payload.rows), saved_to_bank_only=saved_only)


def save_csv_to_bank(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: CsvBankSaveRequest,
) -> CsvBankSaveResponse:
    """Save validated CSV rows without attaching them to a quiz."""
    from app.services.quizzes import _require_active_membership

    _require_active_membership(db, account, class_id)
    for row in payload.rows:
        db.add(
            QuestionBankItem(
                owner_id=account.account_id,
                source_class_id=class_id,
                is_current=True,
                question_text=row.question.question_text,
                explanation=row.question.explanation,
                choices_json=[choice.model_dump() for choice in row.question.choices],
            )
        )
    db.commit()
    return CsvBankSaveResponse(saved_to_bank=len(payload.rows))


def export_csv(db: Session, account: CurrentAccount, class_id: int, scope: BankScope,
               ids: list[int] | None = None) -> str:
    from app.services.quizzes import _require_active_membership
    membership = _require_active_membership(db, account, class_id)
    is_organizer = membership.role == ClassRole.ORGANIZER
    _ensure_legacy_snapshots(
        db, account, class_id, is_organizer=is_organizer
    )
    condition = _visible_condition(
        account, class_id, scope, is_organizer=is_organizer
    ) & QuestionBankItem.is_current.is_(True)
    if ids: condition = condition & QuestionBankItem.bank_question_id.in_(ids)
    items = list(db.scalars(select(QuestionBankItem).where(condition).order_by(QuestionBankItem.bank_question_id)))
    out = io.StringIO(newline=""); writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS); writer.writeheader()
    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text.startswith(("=", "+", "-", "@")) else text
    for item in items:
        choices = list(item.choices_json)[:4]
        row = {"question_text": safe(item.question_text), "explanation": safe(item.explanation),
            "correct_choices": "|".join(chr(65+i) for i,c in enumerate(choices) if c["is_correct"])}
        for index, key in enumerate("abcd"):
            row[f"choice_{key}"] = safe(choices[index]["choice_text"]) if index < len(choices) else ""
        writer.writerow(row)
    return out.getvalue()
