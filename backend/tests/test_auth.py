import pytest

from app.api.routes.quizzes import active_account
from app.auth import CurrentAccount
from app.errors import APIError
from app.models import AccountType


def test_current_account_supports_unassigned_role() -> None:
    account = CurrentAccount(account_id=1, account_type=None)

    assert account.account_id == 1
    assert account.account_type is None
    assert account.is_active is True


def test_inactive_accounts_cannot_use_quiz_routes() -> None:
    account = CurrentAccount(1, AccountType.STUDENT, is_active=False)

    with pytest.raises(APIError) as caught:
        active_account(account)

    assert caught.value.status_code == 403
    assert caught.value.code == "inactive_account"
