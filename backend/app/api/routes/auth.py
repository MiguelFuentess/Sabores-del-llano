from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Usuario
from app.schemas.auth import LoginRequest, TokenResponse, UsuarioPublicResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def post_login(
    payload: LoginRequest,
    session: Session = Depends(get_db),
) -> TokenResponse:
    return auth_service.login_for_access_token(session, payload)


@router.get("/me", response_model=UsuarioPublicResponse)
def get_me(
    current_user: Usuario = Depends(get_current_user),
) -> UsuarioPublicResponse:
    return UsuarioPublicResponse.model_validate(current_user)
