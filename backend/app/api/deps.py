from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Usuario
from app.services.auth import resolve_user_from_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> Usuario:
    """Dependencia de FastAPI que exige un token Bearer válido y un usuario activo."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionaron credenciales de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolve_user_from_token(session, credentials.credentials)
