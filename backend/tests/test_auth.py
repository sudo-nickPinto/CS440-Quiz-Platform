from app.auth import CurrentAccount


def test_current_account_supports_unassigned_role() -> None:
    account = CurrentAccount(account_id=1, account_type=None)

    assert account.account_id == 1
    assert account.account_type is None
    assert account.is_active is True
