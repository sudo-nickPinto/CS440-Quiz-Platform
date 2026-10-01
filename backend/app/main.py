import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials

from app.accounts import get_or_create_account
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

