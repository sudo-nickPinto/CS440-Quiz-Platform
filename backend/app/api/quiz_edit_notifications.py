from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.notifications.events import notify_submission_changed
from app.notifications.hub import NotificationHub
from app.services.quiz_submissions import COMMITTED_QUIZ_WITHDRAWALS

T = TypeVar("T")


def run_quiz_edit_with_notifications(
    db: Session,
    notification_hub: NotificationHub,
    background_tasks: BackgroundTasks,
    edit: Callable[..., T],
    account: CurrentAccount,
    *args: Any,
) -> T:
    result = edit(db, account, *args)
    for submission_id in db.info.pop(COMMITTED_QUIZ_WITHDRAWALS, []):
        background_tasks.add_task(
            notify_submission_changed,
            notification_hub,
            submission_id=submission_id,
            action="withdrawn",
            actor_account_id=account.account_id,
        )
    return result
