src/api/auth/jwt_manager.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Any

import jwt
from fastapi import HTTPException, status


JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TTL_MIN = int(os.getenv("JWT_ACCESS_TTL_MIN", "60"))


def create_access_token(data: Dict[str, Any]) -> str:
    payload = data.copy()

    expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TTL_MIN)

    payload.update(
        {
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }
    )

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return token


def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


-------------------
src/api/auth/security.py
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.api.auth.jwt_manager import verify_access_token


security_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    token = credentials.credentials

    payload = verify_access_token(token)

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return payload
-----

src/api/auth/rate_limiter.py

from __future__ import annotations

import time
from collections import defaultdict
from fastapi import HTTPException


RATE_LIMIT = 60
RATE_WINDOW = 60


requests_store = defaultdict(list)


def rate_limit(user_id: str):

    now = time.time()

    timestamps = requests_store[user_id]

    timestamps[:] = [t for t in timestamps if now - t < RATE_WINDOW]

    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
        )

    timestamps.append(now)

-----------------------

src/api/models_auth.py
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

-----------------

src/api/routes/auth.py
from fastapi import APIRouter, HTTPException

from src.api.models_auth import LoginRequest, TokenResponse
from src.api.auth.jwt_manager import create_access_token


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):

    if req.username != "admin" or req.password != "admin":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        {
            "user_id": req.username,
            "role": "admin",
        }
    )

    return TokenResponse(access_token=token)

-----------------------
src/api/middleware/request_context.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        request.state.request_id = str(uuid.uuid4())

        response = await call_next(request)

        return response


