from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.routes import notifications_live
from app.auth import CurrentAccount
from app.config import Settings
from app.database import Base
from app.live.protocol import CloseCode, LiveCloseError
from app.main import create_app
from app.models.account import Account, AccountRole

URL = "/ws/notifications"


@pytest.fixture
def notification_client(
    monkeypatch,
) -> Iterator[tuple[TestClient, CurrentAccount, CurrentAccount]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            first = Account(
                auth0_sub="auth0|first",
                email="first@example.com",
                display_name="First",
                is_active=True,
            )
            second = Account(
                auth0_sub="auth0|second",
                email="second@example.com",
                display_name="Second",
                is_active=True,
            )
            db.add_all([first, second])
            db.commit()
            accounts = {
                "first-token": CurrentAccount(first.account_id, AccountRole.USER, True),
                "second-token": CurrentAccount(
                    second.account_id, AccountRole.USER, True
                ),
            }

        def fake_authenticate(db, settings, token):
            if token not in accounts:
                raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token")
            return accounts[token]

        monkeypatch.setattr(notifications_live, "authenticate_token", fake_authenticate)
        yield client, accounts["first-token"], accounts["second-token"]


def _authenticate(socket, token: str) -> dict:
    socket.send_json({"type": "auth", "token": token})
    return socket.receive_json()


def test_socket_authenticates_and_receives_ready(notification_client) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        assert _authenticate(socket, "first-token") == {"type": "notifications_ready"}


@pytest.mark.parametrize(
    ("first_message", "code"),
    [
        ({"type": "auth"}, CloseCode.UNAUTHORIZED),
        ({"type": "auth", "token": "bad-token"}, CloseCode.UNAUTHORIZED),
        ({"type": "ping"}, CloseCode.MALFORMED),
    ],
    ids=["missing-token", "invalid-token", "not-auth"],
)
def test_bad_auth_closes_socket(notification_client, first_message, code) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        socket.send_json(first_message)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == code


def test_send_to_accounts_reaches_every_socket_of_listed_accounts_only(
    notification_client,
) -> None:
    client, first, _ = notification_client
    hub = client.app.state.notification_hub
    event = {"type": "test_event", "value": 1}

    with (
        client.websocket_connect(URL) as tab_one,
        client.websocket_connect(URL) as tab_two,
        client.websocket_connect(URL) as other,
    ):
        _authenticate(tab_one, "first-token")
        _authenticate(tab_two, "first-token")
        _authenticate(other, "second-token")

        client.portal.call(
            hub.send_to_accounts, [first.account_id, first.account_id], event
        )

        assert tab_one.receive_json() == event
        assert tab_two.receive_json() == event
        # The other account got nothing: its next message is the pong.
        other.send_json({"type": "ping"})
        assert other.receive_json() == {"type": "pong"}
        # Each tab got the event exactly once despite the duplicate id.
        tab_one.send_json({"type": "ping"})
        assert tab_one.receive_json() == {"type": "pong"}


def test_ping_gets_pong(notification_client) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        _authenticate(socket, "first-token")
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}
