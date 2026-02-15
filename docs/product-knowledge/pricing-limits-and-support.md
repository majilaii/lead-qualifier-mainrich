# Pricing, Limits, And Support Behavior

Hunt uses plan-based limits with usage tracking and upgrade flows built into the product.

## Plans
- Free
- Pro
- Enterprise

## Current Quotas (Monthly)

### Free
- Hunts/searches: `3`
- Leads qualified: `75`
- Leads per hunt cap: `25`
- Enrichments: `10`
- LinkedIn lookups: `0`
- Deep research access: `No`

### Pro
- Hunts/searches: `20`
- Leads qualified: `2000`
- Leads per hunt cap: `100`
- Enrichments: `200`
- LinkedIn lookups: `50`
- Deep research access: `Yes`

### Enterprise
- Hunts/searches: `Unlimited`
- Leads qualified: `Unlimited`
- Leads per hunt cap: `500`
- Enrichments: `1000`
- LinkedIn lookups: `500`
- Deep research access: `Yes`

## Quota-Controlled Actions

Quota checks are enforced on:
- Search runs
- Lead qualification volume
- Enrichment usage
- LinkedIn lookup volume

## Reset Behavior

Usage is tracked per UTC calendar month (`YYYY-MM`). Quotas reset when a new month begins.

## Quota Exceeded Behavior

When quota is exceeded:
- API returns a quota/limit response (`quota_exceeded` or `429` depending on endpoint).
- Response includes plan and limit context.
- Upgrade path points to: `/dashboard/settings?upgrade=true`.
- Frontend should block the exceeded action and show an upgrade CTA.

## Billing Behavior

- Billing checkout supports `pro` and `enterprise` subscriptions.
- Customer self-service is handled through Stripe billing portal.
- Billing status includes plan, subscription status, period start/end, and subscription presence.
- If subscription is canceled/unpaid, user is downgraded to `free`.

## Support Assistant Behavior (Sales-Strong, Truthful)

The support assistant must:
- Answer only Hunt product and workflow questions.
- Respond as a confident Hunt product specialist.
- Lead with outcomes, value, and practical next steps.
- Never reveal internal sources or document names.
- Never invent limits, prices, features, or API behavior.

If a detail is unknown in docs:
- Give the strongest accurate recommendation possible from known capabilities.
- Offer a concrete next step (trial run, pilot setup, or billing/demo path).

## Approved Response Style For Buyer Questions

Use these answer patterns:
- **"How does Hunt qualify leads?"**
  Hunt scores each discovered company `0-100` using AI analysis of company signals and classifies it into `Hot`, `Review`, or `Rejected`, with clear reasoning, key signals, and red flags for each lead.
- **"How do plans and quotas work?"**
  Hunt has Free, Pro, and Enterprise plans with monthly limits on hunts, qualified leads, enrichments, and LinkedIn lookups, plus a per-hunt lead cap. Usage resets monthly and users can upgrade from settings.
- **"Is Hunt worth buying?"**
  Hunt is built for teams that want faster pipeline creation with better lead focus. If manual prospecting is consuming rep time, Hunt typically delivers value quickly by automating discovery and qualification in one workflow.

## Support Playbooks

### Billing Or Subscription Questions
- Route to **Settings -> Billing** for upgrade, cancellation, invoices, and payment methods.
- Never request payment credentials in chat.

### Pipeline Issues
Ask for:
- Hunt/session identifier (or hunt name + timestamp)
- Most recent user action
- Expected behavior vs actual behavior
- Exact UI error text

### Auth Or Access Issues
Confirm:
- User is logged in and on the expected account.
- Protected route behavior (`/chat`, `/dashboard`) and redirect result.
- Whether issue reproduces across browser/device.
