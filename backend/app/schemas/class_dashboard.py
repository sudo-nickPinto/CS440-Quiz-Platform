from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.models.classes import ClassRole
from app.models.quiz_submission import SubmissionStatus
from app.schemas.pagination import PageInfo, SortOrder
from app.schemas.quiz import ClassQuizListItem, QuizHosting, QuizVersionResponse


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


class SubmissionSort(str, Enum):
    SUBMITTED_AT = "submitted_at"
    TITLE = "title"
    SUBMITTER = "submitter"


class ApprovedQuizSort(str, Enum):
    APPROVED_AT = "approved_at"
    TITLE = "title"


class ClassSubmissionSummary(BaseModel):
    submission_id: int
    quiz_id: int
    quiz_version_id: int
    version_number: int
    quiz_title: str
    question_count: int
    submitted_by_id: int
    submitter_name: str
    status: SubmissionStatus
    submitted_at: datetime
    decided_at: datetime | None
    decided_by_name: str | None
    # False once a newer version of the quiz is published; a stale pending
    # submission can only be rejected or withdrawn.
    is_current_version: bool


class ClassSubmissionPreview(BaseModel):
    """Exactly the version that was submitted, never the quiz's newer draft,
    so an organizer reviews what they approve."""

    submission: ClassSubmissionSummary
    version: QuizVersionResponse


class ClassApprovedQuiz(BaseModel):
    quiz_id: int
    quiz_version_id: int
    version_number: int
    title: str
    question_count: int
    author_id: int
    author_name: str
    approved_at: datetime
    approved_by_name: str
    # From the same checks as starting a session (services/hosting.py), so
    # the Host button and the server agree. Only the owner or an active
    # organizer can host, and not while the quiz has unapproved changes.
    can_host: bool
    hosting: QuizHosting
    # Whether the caller may open the quiz page (/quizzes/{id}): the owner,
    # an organizer, or an active collaborator. Other members see the card
    # only.
    can_view: bool


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


class ClassSubmissionPage(BaseModel):
    class_id: int
    items: list[ClassSubmissionSummary]
    pagination: PageInfo


class ClassApprovedQuizPage(BaseModel):
    class_id: int
    items: list[ClassApprovedQuiz]
    pagination: PageInfo


class ClassDashboardResponse(BaseModel):
    class_id: int
    class_name: str
    current_user_role: ClassRole | None
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
    # Quizzes in this class the caller owns or edits as a collaborator.
    my_quizzes: list[ClassQuizListItem]
    my_quiz_count: int
    # Organizers: every pending submission in the class. Members: their own.
    pending_submission_count: int
    approved_quiz_count: int
