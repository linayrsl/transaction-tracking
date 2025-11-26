from fastapi import HTTPException, Request, status
from app.models.user import User


async def get_current_user(request: Request) -> User:
    """
    Get current authenticated user from request state.

    UserInjectionMiddleware has already parsed the JWT and loaded the user.
    This dependency simply retrieves it and raises 401 if not present.

    Args:
        request: FastAPI request object with user in state

    Returns:
        User: The authenticated user

    Raises:
        HTTPException: 401 if user is not authenticated
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(request: Request) -> User | None:
    """
    Get current user if authenticated, otherwise return None.

    Use this for routes that want to customize behavior for authenticated users
    but don't require authentication.

    Args:
        request: FastAPI request object with user in state

    Returns:
        User | None: The authenticated user or None
    """
    return getattr(request.state, "user", None)
