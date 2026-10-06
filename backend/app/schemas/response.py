from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResponseSubmit(BaseModel):
    """The only answer data a participant is allowed to provide."""

    model_config = ConfigDict(extra="forbid")

    choice_id: int = Field(gt=0)


class ResponseReceipt(BaseModel):
    """Safe acknowledgement returned while the question is still open.

    Correctness and points are stored by the server but withheld until the
    question closes so one participant cannot reveal the answer to others.
    """

    model_config = ConfigDict(from_attributes=True)

    response_id: int
    session_question_id: int
    choice_id: int
    submitted_at: datetime
