"""
Tests for auth/__init__.py

Covers JWT decoding, AuthUser model, and FastAPI auth dependencies.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from auth import decode_token, AuthUser, get_current_user, require_auth


# ═══════════════════════════════════════════════
# AuthUser model
# ═══════════════════════════════════════════════

class TestAuthUser:
    def test_creation(self):
        user = AuthUser(id="abc-123", email="a@b.com", role="authenticated")
        assert user.id == "abc-123"
        assert user.email == "a@b.com"
        assert user.role == "authenticated"

    def test_defaults(self):
        user = AuthUser(id="abc")
        assert user.email is None
        assert user.role is None


# ═══════════════════════════════════════════════
# decode_token
# ═══════════════════════════════════════════════

class TestDecodeToken:
    def test_valid_jwks_token(self):
        expected = {"sub": "user-1", "email": "a@b.com", "role": "authenticated"}
        mock_key = MagicMock()
        mock_key.key = "fake-key"

        with patch("auth._get_jwks_client") as mock_jwks, \
             patch("auth.jwt.decode", return_value=expected):
            mock_jwks.return_value.get_signing_key_from_jwt.return_value = mock_key
            result = decode_token("fake.jwt.token")

        assert result == expected

    def test_jwks_fails_hs256_fallback(self):
        expected = {"sub": "user-2", "email": "b@c.com"}

        with patch("auth._get_jwks_client") as mock_jwks, \
             patch("auth._legacy_secret", "my-secret"), \
             patch("auth.jwt.decode") as mock_decode:
            # First call (JWKS) raises; second call (HS256) succeeds
            import jwt as pyjwt
            mock_jwks.return_value.get_signing_key_from_jwt.side_effect = \
                pyjwt.exceptions.PyJWKClientError("no key")
            mock_decode.return_value = expected
            result = decode_token("fake.jwt.token")

        assert result == expected

    def test_both_fail_returns_none(self):
        import jwt as pyjwt
        with patch("auth._get_jwks_client") as mock_jwks, \
             patch("auth._legacy_secret", ""), \
             patch("auth.jwt.decode") as mock_decode:
            mock_jwks.return_value.get_signing_key_from_jwt.side_effect = \
                pyjwt.exceptions.PyJWKClientError("no key")
            mock_decode.side_effect = pyjwt.InvalidTokenError("bad")
            result = decode_token("bad.token")

        assert result is None


# ═══════════════════════════════════════════════
# get_current_user
# ═══════════════════════════════════════════════

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_credentials(self):
        user = await get_current_user(credentials=None)
        assert user is None

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        creds = MagicMock()
        creds.credentials = "bad.token"
        with patch("auth.decode_token", return_value=None):
            user = await get_current_user(credentials=creds)
        assert user is None

    @pytest.mark.asyncio
    async def test_valid_token(self):
        creds = MagicMock()
        creds.credentials = "good.token"
        payload = {"sub": "user-1", "email": "a@b.com", "role": "authenticated"}
        with patch("auth.decode_token", return_value=payload):
            user = await get_current_user(credentials=creds)
        assert isinstance(user, AuthUser)
        assert user.id == "user-1"
        assert user.email == "a@b.com"


# ═══════════════════════════════════════════════
# require_auth
# ═══════════════════════════════════════════════

class TestRequireAuth:
    @pytest.mark.asyncio
    async def test_no_user_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(user=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_user_passes_through(self):
        user = AuthUser(id="user-1", email="a@b.com")
        result = await require_auth(user=user)
        assert result.id == "user-1"
