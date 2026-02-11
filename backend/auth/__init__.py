"""
Auth Middleware — Supabase JWT validation for backend API routes.

Validates JWT access tokens issued by Supabase Auth using the project's
JWKS (JSON Web Key Set) endpoint.  No shared secret required.

Provides ``get_current_user`` / ``require_auth`` FastAPI dependencies.
"""

import os
import logging
import jwt
from jwt import PyJWKClient
from typing import Optional

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Supabase project URL — same as NEXT_PUBLIC_SUPABASE_URL
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://fwtxlbjnjfzqmqqmsssb.supabase.co",
)

# JWKS endpoint for asymmetric key verification (preferred)
_jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client: Optional[PyJWKClient] = None

# Fallback: legacy HS256 shared secret (only if JWKS unavailable)
_legacy_secret = os.getenv("SUPABASE_JWT_SECRET", "")

security = HTTPBearer(auto_error=False)


def _get_jwks_client() -> PyJWKClient:
    """Lazy-init the JWKS client (caches keys for 10 min)."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_jwks_url, cache_jwk_set=True, lifespan=600)
    return _jwks_client


class AuthUser(BaseModel):
    """Authenticated user extracted from Supabase JWT."""
    id: str
    email: Optional[str] = None
    role: Optional[str] = None


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a Supabase JWT access token.

    Tries JWKS (asymmetric) first, falls back to legacy HS256 secret.
    """
    # --- Try JWKS (RS256 / ES256) ---
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
        return payload
    except (jwt.exceptions.PyJWKClientError, jwt.InvalidTokenError) as e:
        logger.debug("JWKS verification failed (%s), trying HS256 fallback", e)

    # --- Fallback: legacy HS256 shared secret ---
    if _legacy_secret:
        try:
            payload = jwt.decode(
                token,
                _legacy_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_exp": True},
            )
            return payload
        except jwt.InvalidTokenError:
            pass

    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthUser]:
    """Extract the current user from the Authorization header.

    Returns ``None`` if no valid token is present (anonymous access).
    Use ``require_auth`` instead to enforce authentication.
    """
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload:
        return None

    return AuthUser(
        id=payload.get("sub", ""),
        email=payload.get("email"),
        role=payload.get("role"),
    )


async def require_auth(
    user: Optional[AuthUser] = Depends(get_current_user),
) -> AuthUser:
    """Dependency that enforces authentication.

    Raises 401 if no valid user is found.
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
