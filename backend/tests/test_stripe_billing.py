"""
Tests for stripe_billing.py

Covers configuration helpers, plan maps, checkout, portal, billing status,
and all four webhook sub-handlers.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stripe_billing import (
    is_stripe_configured,
    PLAN_PRICE_MAP,
    PRICE_PLAN_MAP,
    create_checkout_session,
    create_portal_session,
    get_billing_status,
    handle_webhook,
    _handle_checkout_completed,
    _handle_subscription_updated,
    _handle_subscription_deleted,
    _handle_payment_failed,
)


def _fake_to_thread(return_val):
    """Create a coroutine function that ignores args and returns return_val."""
    async def _coro(*args, **kwargs):
        return return_val
    return _coro

# ── helpers to build a fake Profile row ────────

class FakeProfile:
    """Lightweight stand-in for db.models.Profile to test attribute mutations."""
    def __init__(self, **kw):
        self.id = kw.get("id", "user-1")
        self.email = kw.get("email", "user@test.com")
        self.plan = kw.get("plan", "free")
        self.plan_tier = kw.get("plan_tier", "free")
        self.stripe_customer_id = kw.get("stripe_customer_id", None)
        self.stripe_subscription_id = kw.get("stripe_subscription_id", None)
        self.plan_period_start = kw.get("plan_period_start", None)
        self.plan_period_end = kw.get("plan_period_end", None)


def _mock_db_with_profile(profile):
    """Return a mock AsyncSession whose execute() returns the given profile."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = profile

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _mock_db_no_profile():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ═══════════════════════════════════════════════
# Configuration helpers
# ═══════════════════════════════════════════════

class TestStripeConfig:
    def test_is_configured_true(self):
        with patch("stripe_billing.STRIPE_SECRET_KEY", "sk_test_abc"), \
             patch("stripe_billing.STRIPE_PRO_PRICE_ID", "price_123"):
            assert is_stripe_configured() is True

    def test_is_configured_no_key(self):
        with patch("stripe_billing.STRIPE_SECRET_KEY", ""), \
             patch("stripe_billing.STRIPE_PRO_PRICE_ID", "price_123"):
            assert is_stripe_configured() is False

    def test_is_configured_no_price(self):
        with patch("stripe_billing.STRIPE_SECRET_KEY", "sk_test"), \
             patch("stripe_billing.STRIPE_PRO_PRICE_ID", ""):
            assert is_stripe_configured() is False

    def test_plan_price_map_has_pro_and_enterprise(self):
        assert "pro" in PLAN_PRICE_MAP
        assert "enterprise" in PLAN_PRICE_MAP

    def test_price_plan_reverse_lookup(self):
        # PRICE_PLAN_MAP should be the inverse of PLAN_PRICE_MAP (minus empty values)
        for plan, price_id in PLAN_PRICE_MAP.items():
            if price_id:
                assert PRICE_PLAN_MAP.get(price_id) == plan


# ═══════════════════════════════════════════════
# Checkout session
# ═══════════════════════════════════════════════

class TestCheckoutSession:
    @pytest.mark.asyncio
    async def test_unknown_plan_raises(self):
        db = _mock_db_no_profile()
        with pytest.raises(ValueError, match="Unknown plan"):
            await create_checkout_session(db, "user-1", "a@b.com", "platinum")

    @pytest.mark.asyncio
    async def test_creates_session_for_existing_customer(self):
        profile = FakeProfile(stripe_customer_id="cus_abc")
        db = _mock_db_with_profile(profile)

        fake_session = MagicMock()
        fake_session.url = "https://checkout.stripe.com/s/123"

        with patch("stripe_billing.PLAN_PRICE_MAP", {"pro": "price_pro"}), \
             patch("stripe_billing.asyncio.to_thread", side_effect=_fake_to_thread(fake_session)):
            url = await create_checkout_session(db, "user-1", "a@b.com", "pro")

        assert url == "https://checkout.stripe.com/s/123"


# ═══════════════════════════════════════════════
# Portal session
# ═══════════════════════════════════════════════

class TestPortalSession:
    @pytest.mark.asyncio
    async def test_no_customer_raises(self):
        profile = FakeProfile(stripe_customer_id=None)
        db = _mock_db_with_profile(profile)
        with pytest.raises(ValueError, match="No Stripe customer"):
            await create_portal_session(db, "user-1")

    @pytest.mark.asyncio
    async def test_creates_portal_url(self):
        profile = FakeProfile(stripe_customer_id="cus_abc")
        db = _mock_db_with_profile(profile)

        fake_session = MagicMock()
        fake_session.url = "https://billing.stripe.com/portal/x"

        with patch("stripe_billing.asyncio.to_thread", side_effect=_fake_to_thread(fake_session)):
            url = await create_portal_session(db, "user-1")

        assert url == "https://billing.stripe.com/portal/x"


# ═══════════════════════════════════════════════
# Billing status
# ═══════════════════════════════════════════════

class TestBillingStatus:
    @pytest.mark.asyncio
    async def test_no_profile_returns_free(self):
        db = _mock_db_no_profile()
        status = await get_billing_status(db, "user-x")
        assert status["plan"] == "free"
        assert status["has_subscription"] is False

    @pytest.mark.asyncio
    async def test_profile_without_subscription(self):
        profile = FakeProfile(plan="pro", stripe_subscription_id=None)
        db = _mock_db_with_profile(profile)
        status = await get_billing_status(db, "user-1")
        assert status["plan"] == "pro"
        assert status["status"] == "none"
        assert status["has_subscription"] is False

    @pytest.mark.asyncio
    async def test_active_subscription(self):
        profile = FakeProfile(
            plan="pro",
            stripe_subscription_id="sub_123",
            stripe_customer_id="cus_abc",
            plan_period_end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        db = _mock_db_with_profile(profile)

        fake_sub = MagicMock()
        fake_sub.status = "active"

        with patch("stripe_billing.asyncio.to_thread", side_effect=_fake_to_thread(fake_sub)):
            status = await get_billing_status(db, "user-1")

        assert status["plan"] == "pro"
        assert status["status"] == "active"
        assert status["has_subscription"] is True


# ═══════════════════════════════════════════════
# Webhook: handle_webhook dispatch
# ═══════════════════════════════════════════════

class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_invalid_payload_raises(self):
        db = AsyncMock()

        async def _raise_value_error(*a, **kw):
            raise ValueError("Invalid payload")

        with patch("stripe_billing.asyncio.to_thread", side_effect=_raise_value_error):
            with pytest.raises(ValueError, match="Invalid payload"):
                await handle_webhook(b"bad", "sig", db)


# ═══════════════════════════════════════════════
# Webhook sub-handlers
# ═══════════════════════════════════════════════

class TestCheckoutCompleted:
    @pytest.mark.asyncio
    async def test_activates_plan(self):
        profile = FakeProfile(plan="free")
        db = _mock_db_with_profile(profile)

        session_data = {
            "customer": "cus_abc",
            "subscription": "sub_123",
            "metadata": {"user_id": "user-1", "plan": "pro"},
        }

        fake_sub = MagicMock()
        fake_sub.current_period_start = 1700000000
        fake_sub.current_period_end = 1703000000

        with patch("stripe_billing.asyncio.to_thread", side_effect=_fake_to_thread(fake_sub)):
            await _handle_checkout_completed(session_data, db)

        assert profile.plan == "pro"
        assert profile.stripe_customer_id == "cus_abc"
        assert profile.stripe_subscription_id == "sub_123"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_user_id_lookup_by_customer(self):
        profile = FakeProfile(id="found-user")
        db = _mock_db_with_profile(profile)

        session_data = {
            "customer": "cus_abc",
            "subscription": "sub_123",
            "metadata": {},
        }

        fake_sub = MagicMock()
        fake_sub.current_period_start = 1700000000
        fake_sub.current_period_end = 1703000000

        with patch("stripe_billing.asyncio.to_thread", side_effect=_fake_to_thread(fake_sub)):
            await _handle_checkout_completed(session_data, db)

        assert profile.plan == "pro"


class TestSubscriptionUpdated:
    @pytest.mark.asyncio
    async def test_updates_plan_from_price_id(self):
        profile = FakeProfile(plan="pro")
        db = _mock_db_with_profile(profile)

        sub_data = {
            "customer": "cus_abc",
            "id": "sub_456",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_ent"}}]},
            "current_period_start": 1700000000,
            "current_period_end": 1703000000,
        }

        with patch("stripe_billing.PRICE_PLAN_MAP", {"price_ent": "enterprise"}):
            await _handle_subscription_updated(sub_data, db)

        assert profile.plan == "enterprise"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_canceled_status_downgrades(self):
        profile = FakeProfile(plan="pro")
        db = _mock_db_with_profile(profile)

        sub_data = {
            "customer": "cus_abc",
            "id": "sub_456",
            "status": "canceled",
            "items": {"data": []},
        }

        await _handle_subscription_updated(sub_data, db)
        assert profile.plan == "free"


class TestSubscriptionDeleted:
    @pytest.mark.asyncio
    async def test_downgrades_to_free(self):
        profile = FakeProfile(
            plan="pro",
            stripe_subscription_id="sub_123",
        )
        db = _mock_db_with_profile(profile)

        await _handle_subscription_deleted({"customer": "cus_abc"}, db)

        assert profile.plan == "free"
        assert profile.plan_tier == "free"
        assert profile.stripe_subscription_id is None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_profile_is_noop(self):
        db = _mock_db_no_profile()
        # Should not raise
        await _handle_subscription_deleted({"customer": "cus_unknown"}, db)


class TestPaymentFailed:
    @pytest.mark.asyncio
    async def test_logs_warning(self):
        profile = FakeProfile()
        db = _mock_db_with_profile(profile)
        # Should not raise, just logs
        await _handle_payment_failed({"customer": "cus_abc", "attempt_count": 2}, db)

    @pytest.mark.asyncio
    async def test_unknown_customer_no_crash(self):
        db = _mock_db_no_profile()
        await _handle_payment_failed({"customer": "cus_unknown", "attempt_count": 1}, db)
