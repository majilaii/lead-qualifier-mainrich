# 🧲 The Magnet Hunter — Free Platform Plan

## Target Users
- **Chinese B2B companies** looking for international buyers/suppliers
- **Serbian B2B companies** expanding into new markets
- General hardware/manufacturing B2B sales teams

## Free Tier (Current Groundwork)

### What Free Users Get
| Feature | Free | Pro ($49/mo) | Enterprise |
|---------|------|--------------|------------|
| Leads / month | 50 | 1,000 | Unlimited |
| AI qualification | Basic | Advanced + Vision | Custom models |
| Deep research briefs | ❌ | ✅ | ✅ |
| Contact enrichment | ❌ | ✅ | ✅ |
| Saved searches | 3 | Unlimited | Unlimited |
| Export | CSV only | Excel + CRM | API + custom |
| Team seats | 1 | 3 | Unlimited |
| Support | Community | Priority | Dedicated AM |

### User Journey (Free Tier)
```
1. Landing page → "Get Started Free" CTA
2. /signup → Create account (email + password, or Google/WeChat OAuth)
3. /dashboard → Onboarding wizard
   a. "What does your company sell?"
   b. "Who is your ideal customer?"
   c. "What industries do you target?"
4. /chat → AI chat interface (existing) — free users get 50 leads/mo
5. Results → View qualified leads, export CSV
6. Upgrade prompt when hitting limits
```

## TODO — Backend Auth & Platform

### Phase 1: Auth (Next Priority)
- [ ] Set up auth provider (NextAuth.js or Clerk)
- [ ] Google OAuth integration
- [ ] WeChat OAuth integration (for Chinese users)
- [ ] Email/password auth with verification
- [ ] Protected routes: /chat, /dashboard
- [ ] User session management

### Phase 2: Dashboard
- [ ] /dashboard page with usage stats
- [ ] Lead history (past searches & results)
- [ ] Saved search configurations
- [ ] Usage meter (X/50 leads used this month)
- [ ] Quick actions: new search, export history, upgrade

### Phase 3: Usage Limits & Billing
- [ ] Track leads per user per month
- [ ] Enforce 50 lead limit for free tier
- [ ] Stripe integration for Pro tier
- [ ] Upgrade/downgrade flow
- [ ] Invoice history

### Phase 4: Localization
- [ ] i18n setup (next-intl or similar)
- [ ] Chinese (Simplified) translations
- [ ] Serbian translations
- [ ] Currency localization (CNY, RSD, USD, EUR)
- [ ] Region-specific landing pages

### Phase 5: Team & Enterprise
- [ ] Team invitation system
- [ ] Role-based access (admin, member, viewer)
- [ ] Shared lead pools
- [ ] API key management
- [ ] White-label customization

## File Structure Plan
```
frontend/src/app/
├── (auth)/
│   ├── login/page.tsx        ✅ Created
│   └── signup/page.tsx       ✅ Created
├── (platform)/
│   ├── dashboard/page.tsx    🔲 TODO
│   ├── history/page.tsx      🔲 TODO
│   └── settings/page.tsx     🔲 TODO
├── chat/page.tsx             ✅ Exists
├── components/
│   ├── Navbar.tsx            ✅ Updated
│   ├── Pricing.tsx           ✅ Created
│   ├── ...                   ✅ Updated
│   └── auth/
│       ├── AuthGuard.tsx     🔲 TODO
│       └── UserMenu.tsx      🔲 TODO
└── api/
    ├── auth/
    │   └── [...nextauth]/    🔲 TODO
    └── chat/                 ✅ Exists
```

## Current Status
- ✅ Landing page cleaned up (no tech stack exposure)
- ✅ Sign-up page with form + social login placeholders
- ✅ Login page with form + social login placeholders  
- ✅ Pricing section (Free/Pro/Enterprise tiers)
- ✅ Navbar updated with Log In + Get Started Free
- ✅ Footer updated with Product/Company links
- ✅ CTA updated for SaaS free trial messaging
- 🔲 Auth backend not yet wired
- 🔲 Dashboard not yet built
- 🔲 Usage tracking not yet implemented
- 🔲 i18n not yet set up
