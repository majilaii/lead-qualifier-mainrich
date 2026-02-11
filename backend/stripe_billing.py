"""
Stripe Billing — Checkout, webhooks, portal, and plan management.

Handles the full Stripe billing lifecycle:
  - Creating Checkout Sessions for new subscriptions
  - Processing webhooks (subscription create/update/delete, payment failures)
  - Generating Customer Portal sessions for self-service plan management
  - Querying current plan status + usage for authenticated users

Environment variables:
  STRIPE_SECRET_KEY      — Stripe secret key (sk_live_... or sk_test_...)
  STRIPE_WEBHOOK_SECRET  — Webhook signing secret (whsec_...)
  STRIPE_PRO_PRICE_ID    — Stripe Price ID for Pro plan ($49/mo)
  STRIPE_ENT_PRICE_ID    — Stripe Price ID for Enterprise plan ($199/mo)
  FRONTEND_URL           — Base URL for redirect after checkout (e.g. https://app.hunt.so)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_PRO_PRICE_ID,
    STRIPE_ENT_PRICE_ID,
    FRONTEND_URL,
)
from db.models import Profile

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Stripe Configuration
# ──────────────────────────────────────────────

stripe.api_key = STRIPE_SECRET_KEY

# Plan ID → Price ID mapping
PLAN_PRICE_MAP = {
    "pro": STRIPE_PRO_PRICE_ID,
    "enterprise": STRIPE_ENT_PRICE_ID,
}

# Price ID → Plan name (reverse lookup for webhooks)
PRICE_PLAN_MAP = {v: k for k, v in PLAN_PRICE_MAP.items() if v}


def is_stripe_configured() -> bool:
    """Check if Stripe is properly configured."""
    return bool(STRIPE_SECRET_KEY and STRIPE_PRO_PRICE_ID)


# ──────────────────────────────────────────────
# Checkout Session
# ──────────────────────────────────────────────

async def create_checkout_session(
    db: AsyncSession,
    user_id: str,
    user_email: str,
    plan: str,
) -> str:
    """
    Create a Stripe Checkout Session for a subscription.

    Returns the Checkout Session URL to redirect the user to.
    """
    price_id = PLAN_PRICE_MAP.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}. Must be 'pro' or 'enterprise'.")

    # Get or create Stripe customer
    profile = (await db.execute(
        select(Profile).where(Profile.id == user_id)
    )).scalar_one_or_none()

    customer_id = profile.stripe_customer_id if profile else None

    if not customer_id:
        # Create a new Stripe customer
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email=user_email,
            metadata={"user_id": user_id},
        )
        customer_id = customer.id

        # Save customer ID to profile
        if profile:
            profile.stripe_customer_id = customer_id
            await db.commit()

    # Create Checkout Session
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{FRONTEND_URL}/dashboard?billing=success",
        cancel_url=f"{FRONTEND_URL}/dashboard/settings?billing=cancelled",
        metadata={"user_id": user_id, "plan": plan},
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )

    return session.url


# ──────────────────────────────────────────────
# Customer Portal
# ──────────────────────────────────────────────

async def create_portal_session(db: AsyncSession, user_id: str) -> str:
    """
    Create a Stripe Customer Portal session for managing subscriptions.

    Returns the portal URL.
    """
    profile = (await db.execute(
        select(Profile).where(Profile.id == user_id)
    )).scalar_one_or_none()

    if not profile or not profile.stripe_customer_id:
        raise ValueError("No Stripe customer found. Subscribe to a plan first.")

    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=profile.stripe_customer_id,
        return_url=f"{FRONTEND_URL}/dashboard/settings",
    )

    return session.url


# ──────────────────────────────────────────────
# Billing Status
# ──────────────────────────────────────────────

async def get_billing_status(db: AsyncSession, user_id: str) -> dict:
    """
    Return the current billing/plan status for a user.

    Returns:
        {
            "plan": "free" | "pro" | "enterprise",
            "status": "active" | "canceled" | "past_due" | "none",
            "period_end": "2026-03-11T...",
            "stripe_customer_id": "cus_...",
            "has_subscription": true/false,
        }
    """
    profile = (await db.execute(
        select(Profile).where(Profile.id == user_id)
    )).scalar_one_or_none()

    if not profile:
        return {
            "plan": "free",
            "status": "none",
            "period_end": None,
            "stripe_customer_id": None,
            "has_subscription": False,
        }

    # If there's a subscription, check its current status from Stripe
    sub_status = "none"
    if profile.stripe_subscription_id:
        try:
            sub = await asyncio.to_thread(
                stripe.Subscription.retrieve, profile.stripe_subscription_id
            )
            sub_status = sub.status  # active, canceled, past_due, etc.
        except stripe.error.InvalidRequestError:
            sub_status = "expired"

    return {
        "plan": profile.plan or "free",
        "status": sub_status if profile.stripe_subscription_id else "none",
        "period_end": profile.plan_period_end.isoformat() if profile.plan_period_end else None,
        "period_start": profile.plan_period_start.isoformat() if profile.plan_period_start else None,
        "stripe_customer_id": profile.stripe_customer_id,
        "has_subscription": bool(profile.stripe_subscription_id),
    }


# ──────────────────────────────────────────────
# Webhook Handler
# ──────────────────────────────────────────────

async def handle_webhook(payload: bytes, sig_header: str, db: AsyncSession) -> dict:
    """
    Process a Stripe webhook event.

    Verifies the signature, then dispatches to the appropriate handler.
    Returns a dict with the event type and result.
    """
    try:
        event = await asyncio.to_thread(
            stripe.Webhook.construct_event,
            payload, sig_header, STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise ValueError("Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, db)
    else:
        logger.debug("Unhandled webhook event: %s", event_type)

    return {"event": event_type, "handled": True}


async def _handle_checkout_completed(session_data: dict, db: AsyncSession):
    """Handle successful checkout — activate subscription."""
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")
    user_id = session_data.get("metadata", {}).get("user_id")
    plan = session_data.get("metadata", {}).get("plan", "pro")

    if not user_id:
        # Try to find user by Stripe customer ID
        profile = (await db.execute(
            select(Profile).where(Profile.stripe_customer_id == customer_id)
        )).scalar_one_or_none()
        if not profile:
            logger.error("Checkout completed but no user found for customer %s", customer_id)
            return
        user_id = profile.id
    else:
        profile = (await db.execute(
            select(Profile).where(Profile.id == user_id)
        )).scalar_one_or_none()

    if not profile:
        logger.error("Profile not found for user %s", user_id)
        return

    # Fetch subscription details for period dates
    if subscription_id:
        try:
            sub = await asyncio.to_thread(
                stripe.Subscription.retrieve, subscription_id
            )
            profile.plan_period_start = datetime.fromtimestamp(
                sub.current_period_start, tz=timezone.utc
            )
            profile.plan_period_end = datetime.fromtimestamp(
                sub.current_period_end, tz=timezone.utc
            )
        except Exception as e:
            logger.warning("Could not fetch subscription details: %s", e)

    profile.stripe_customer_id = customer_id
    profile.stripe_subscription_id = subscription_id
    profile.plan = plan
    profile.plan_tier = plan  # Keep plan_tier in sync

    await db.commit()
    logger.info("✅ User %s subscribed to %s plan", user_id, plan)


async def _handle_subscription_updated(sub_data: dict, db: AsyncSession):
    """Handle subscription updates — plan changes, renewals."""
    customer_id = sub_data.get("customer")
    subscription_id = sub_data.get("id")
    status = sub_data.get("status")

    profile = (await db.execute(
        select(Profile).where(Profile.stripe_customer_id == customer_id)
    )).scalar_one_or_none()

    if not profile:
        logger.warning("Subscription updated but no profile for customer %s", customer_id)
        return

    profile.stripe_subscription_id = subscription_id

    # Determine plan from price ID
    items = sub_data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan = PRICE_PLAN_MAP.get(price_id, profile.plan)
        profile.plan = plan
        profile.plan_tier = plan

    # Update period dates
    if sub_data.get("current_period_start"):
        profile.plan_period_start = datetime.fromtimestamp(
            sub_data["current_period_start"], tz=timezone.utc
        )
    if sub_data.get("current_period_end"):
        profile.plan_period_end = datetime.fromtimestamp(
            sub_data["current_period_end"], tz=timezone.utc
        )

    # If subscription is canceled or past_due, handle accordingly
    if status in ("canceled", "unpaid"):
        profile.plan = "free"
        profile.plan_tier = "free"

    await db.commit()
    logger.info("Subscription updated for customer %s: plan=%s, status=%s", customer_id, profile.plan, status)


async def _handle_subscription_deleted(sub_data: dict, db: AsyncSession):
    """Handle subscription cancellation — downgrade to free."""
    customer_id = sub_data.get("customer")

    profile = (await db.execute(
        select(Profile).where(Profile.stripe_customer_id == customer_id)
    )).scalar_one_or_none()

    if not profile:
        logger.warning("Subscription deleted but no profile for customer %s", customer_id)
        return

    profile.plan = "free"
    profile.plan_tier = "free"
    profile.stripe_subscription_id = None
    profile.plan_period_start = None
    profile.plan_period_end = None

    await db.commit()
    logger.info("⬇️ User %s downgraded to free (subscription deleted)", profile.id)


async def _handle_payment_failed(invoice_data: dict, db: AsyncSession):
    """Handle failed payment — log warning (Stripe will retry automatically)."""
    customer_id = invoice_data.get("customer")
    attempt = invoice_data.get("attempt_count", 0)

    profile = (await db.execute(
        select(Profile).where(Profile.stripe_customer_id == customer_id)
    )).scalar_one_or_none()

    if profile:
        logger.warning(
            "⚠️ Payment failed for user %s (attempt %d). Stripe will retry.",
            profile.id, attempt,
        )
    else:
        logger.warning("Payment failed for unknown customer %s", customer_id)
