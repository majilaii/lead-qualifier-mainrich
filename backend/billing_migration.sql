-- ============================================================
-- Billing Migration — Add Stripe columns to profiles table
--
-- Run this in your Supabase SQL Editor AFTER the initial migration.
-- Adds Stripe billing fields needed for SaaS plan enforcement.
-- ============================================================

-- Add Stripe billing columns to profiles
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan_period_start TIMESTAMPTZ;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS plan_period_end TIMESTAMPTZ;

-- Index for fast Stripe customer lookups (webhook handling)
CREATE INDEX IF NOT EXISTS ix_profiles_stripe_customer ON profiles(stripe_customer_id);

-- Add enrichments counter to usage_tracking
ALTER TABLE usage_tracking ADD COLUMN IF NOT EXISTS enrichments_used INTEGER NOT NULL DEFAULT 0;
