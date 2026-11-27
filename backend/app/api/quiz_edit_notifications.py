from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.notifications.events import notify_submission_changed
from app.notifications.hub import NotificationHub
from app.services.quiz_submissions import COMMITTED_QUIZ_WITHDRAWALS

T = TypeVar("T")


async def run_quiz_edit_with_notifications(
    notification_hub: NotificationHub,
    background_tasks: BackgroundTasks,
    edit: Callable[..., T],
    account: CurrentAccount,
    *args: Any,
) -> T:
    withdrawals: list[int] = []

    def save(db: Session) -> T:
        try:
            return edit(db, account, *args)
        finally:
            withdrawals.extend(db.info.pop(COMMITTED_QUIZ_WITHDRAWALS, []))

    succeeded = False
    try:
        result = await notification_hub.run_db(save)
        succeeded = True
        return result
    finally:
        for submission_id in withdrawals:
            notify = partial(
                notify_submission_changed,
                notification_hub,
                submission_id=submission_id,
                action="withdrawn",
                actor_account_id=account.account_id,
            )
            if succeeded:
                background_tasks.add_task(notify)
            else:
                # Background tasks are dropped when a route raises. The
                # edit may already be committed, so deliver before reraising.
                await notify()
