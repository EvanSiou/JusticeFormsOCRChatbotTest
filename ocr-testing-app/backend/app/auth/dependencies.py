"""
Authentication dependencies for FastAPI.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.utils import decode_access_token
from app.models.user import TokenData, UserResponse
from app.services.firestore import FirestoreService

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """
    Dependency to get the current authenticated user from JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token
    token_data = decode_access_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception

    # Get user from database
    firestore = FirestoreService()
    user = await firestore.get_user_by_id(token_data.user_id)

    if user is None:
        raise credentials_exception

    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
    )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to get just the current user's ID from JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception

    return token_data.user_id


async def get_current_user_name(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Dependency to get the current user's display name (email) from JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception

    return token_data.email
