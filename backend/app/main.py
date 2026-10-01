import os
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.accounts import COLUMNS, get_or_create_account
from app.auth import bearer, current_user
from app.db import get_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Quiz Platform API"}


def current_account(
    claims: dict = Depends(current_user),
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db=Depends(get_db),
) -> dict:
    return get_or_create_account(db, claims["sub"], creds.credentials)


@app.get("/me")
def me(account: dict = Depends(current_account)):
    return account


class AccountTypeBody(BaseModel):
    account_type: Literal["STUDENT", "PROFESSOR"]  # ADMINISTRATOR is set by hand only


@app.post("/me/account-type")
def set_account_type(body: AccountTypeBody, account: dict = Depends(current_account), db=Depends(get_db)):
    with db.cursor() as cur:
        cur.execute(
            "UPDATE account SET account_type = %s WHERE account_id = %s AND account_type IS NULL",
            (body.account_type, account["account_id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "Account type is already set")
        cur.execute(f"SELECT {COLUMNS} FROM account WHERE account_id = %s", (account["account_id"],))
        return cur.fetchone()
