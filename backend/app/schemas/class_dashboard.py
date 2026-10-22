from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.classes import ClassRole


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class QuizSort(str, Enum):
    PRESENTED_AT = "presented_at"
    TITLE = "title"
    PARTICIPANT_COUNT = "participant_count"


class SessionSort(str, Enum):
    STARTED_AT = "started_at"
    PARTICIPANT_COUNT = "participant_count"
    AVERAGE_SCORE = "average_score"


class StudentSort(str, Enum):
    NAME = "name"
    AVERAGE_SCORE = "average_score"
    SESSION_COUNT = "session_count"


class PageInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class DependencyState(BaseModel):
    is_complete: bool
    blocked_by: list[str] = Field(default_factory=list)


class ClassQuizSummary(BaseModel):
    quiz_id: int
    title: str
    presented_at: datetime | None
    session_count: int
    participant_count: int
    average_score: float | None


class ClassSessionSummary(BaseModel):
    session_id: int
    quiz_id: int
    quiz_title: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    participant_count: int
    average_score: float | None


class ClassStudentSummary(BaseModel):
    account_id: int
    display_name: str
    email: str
    role: ClassRole
    session_count: int | None
    average_score: float | None
    total_points: int | None


class ClassQuizPage(BaseModel):
    class_id: int
    items: list[ClassQuizSummary]
    pagination: PageInfo
    dependency: DependencyState


class ClassSessionPage(BaseModel):
    class_id: int
    items: list[ClassSessionSummary]
    pagination: PageInfo
    dependency: DependencyState


class ClassStudentPage(BaseModel):
    class_id: int
    items: list[ClassStudentSummary]
    pagination: PageInfo
    dependency: DependencyState


class ClassDashboardResponse(BaseModel):
    class_id: int
    class_name: str
    current_user_role: ClassRole | None
    is_global_admin: bool
    is_archived: bool
    active_member_count: int
    active_sessions: list[ClassSessionSummary]
    completed_sessions: list[ClassSessionSummary]
    presented_quizzes: list[ClassQuizSummary]
    students: list[ClassStudentSummary] | None
    dependency: DependencyState
