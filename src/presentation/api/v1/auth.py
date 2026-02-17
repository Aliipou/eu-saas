"""Authentication API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from application.services.auth_service import AuthenticationError, AuthService, InvalidTokenError
from infrastructure.container import get_auth_service

from .schemas import (
    ErrorResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

if TYPE_CHECKING:
    from domain.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        201: {"description": "User created."},
        409: {"description": "Email already registered.", "model": ErrorResponse},
        422: {"description": "Validation error.", "model": ErrorResponse},
    },
)
async def register(
    body: UserRegister,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    tenant_id_str = request.headers.get("X-Tenant-ID")
    if not tenant_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required.",
        )
    tenant_id = uuid.UUID(tenant_id_str)
    user = service.register_user(
        tenant_id=tenant_id,
        email=body.email,
        password=body.password.get_secret_value(),
        full_name=body.full_name,
    )
    return _user_to_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and obtain tokens",
    responses={
        200: {"description": "Login successful."},
        401: {"description": "Invalid credentials.", "model": ErrorResponse},
    },
)
async def login(
    body: UserLogin,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        token_pair = service.authenticate(
            email=body.email,
            password=body.password.get_secret_value(),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    responses={
        200: {"description": "Tokens refreshed."},
        401: {"description": "Invalid or expired refresh token.", "model": ErrorResponse},
    },
)
async def refresh_token(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
        )
    try:
        token_pair = service.refresh_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out (invalidate refresh token)",
    response_class=Response,
)
async def logout(request: Request) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    responses={
        200: {"description": "Current user profile."},
        401: {"description": "Not authenticated.", "model": ErrorResponse},
    },
)
async def me(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user = service.get_current_user(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return _user_to_response(user)
