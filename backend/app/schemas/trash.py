from datetime import datetime

from pydantic import BaseModel

from app.models.session import LiveSessionStatus


class TrashedClass(BaseModel):
    class_id: int
    name: str
    semester: str | None
    archived: bool
    deleted_at: datetime


class TrashedQuiz(BaseModel):
    quiz_id: int
    title: str
    class_id: int | None
    class_name: str | None
    # The quiz's class is in the trash too, so restore the class first.
    class_in_trash: bool
    deleted_at: datetime


class TrashedSession(BaseModel):
    session_id: int
    quiz_id: int
    quiz_title: str
    class_id: int | None
    class_name: str | None
    class_in_trash: bool
    status: LiveSessionStatus
    ended_at: datetime | None
    deleted_at: datetime


class TrashResponse(BaseModel):
    """What the caller can restore, newest first in each list."""

    classes: list[TrashedClass]
    quizzes: list[TrashedQuiz]
    sessions: list[TrashedSession]
