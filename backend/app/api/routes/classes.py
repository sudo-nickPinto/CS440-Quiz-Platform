from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.classes import ClassCreate, ClassResponse, ClassUpdate
from app.services.classes import (
    archive_class,
    create_class,
    get_class,
    list_classes,
    rotate_class_code,
    update_class,
)

router = APIRouter(prefix="/classes", tags=["classes"])


@router.post("", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
def create_class_route(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassResponse:
    return create_class(db, account, payload)


@router.get("", response_model=list[ClassResponse])
def list_classes_route(
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[ClassResponse]:
    return list_classes(db, account)


@router.get("/{class_id}", response_model=ClassResponse)
def get_class_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassResponse:
    return get_class(db, account, class_id)


@router.patch("/{class_id}", response_model=ClassResponse)
def update_class_route(
    class_id: int,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassResponse:
    return update_class(db, account, class_id, payload)


@router.post("/{class_id}/code", response_model=ClassResponse)
def rotate_class_code_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassResponse:
    return rotate_class_code(db, account, class_id)


@router.post("/{class_id}/archive", response_model=ClassResponse)
def archive_class_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassResponse:
    return archive_class(db, account, class_id)
