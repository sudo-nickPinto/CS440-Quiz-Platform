from datetime import datetime
from enum import Enum

from pydantic import BaseModel

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
    host_name: str
    is_host: bool
    started_at: datetime | None
    ended_at: datetime | None
    participant_count: int
    # Class-wide scores are for organizers; members get null here.
    average_score: float | None
    top_score: int | None
    # The caller's own result, or null if they didn't play.
    my_score: int | None
    my_rank: int | None


class ClassStudentSummary(BaseModel):
    account_id: int
    display_name: str
    email: str
    role: ClassRole
    session_count: int
    average_score: float | None
    total_points: int
    # Share of the class's completed sessions this student played, 0 to 1.
    attendance_rate: float | None
    # Up to five most recent scores, newest first; null where they were absent.
    recent_scores: list[int | None]


class ClassQuizPage(BaseModel):
    class_id: int
    items: list[ClassQuizSummary]
    pagination: PageInfo


class ClassSessionPage(BaseModel):
    class_id: int
    items: list[ClassSessionSummary]
    pagination: PageInfo


class ClassStudentPage(BaseModel):
    class_id: int
    items: list[ClassStudentSummary]
    pagination: PageInfo


class ClassDashboardResponse(BaseModel):
    class_id: int
    class_name: str
    current_user_role: ClassRole | None
    is_global_admin: bool
    is_archived: bool
    active_member_count: int
    student_count: int
    completed_session_count: int
    # Organizer-only aggregates; null for members.
    class_average: float | None
    attendance_rate: float | None
    active_sessions: list[ClassSessionSummary]
    completed_sessions: list[ClassSessionSummary]
    presented_quizzes: list[ClassQuizSummary]
    students: list[ClassStudentSummary] | None
