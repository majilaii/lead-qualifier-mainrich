"""
Reddit Signals Module — Market Sentiment & Buying Intent from Reddit

Taps into Reddit via PullPush (free, no auth, no approval needed) to find:
  1. Buying intent signals ("looking for a supplier", "recommend a tool")
  2. Market sentiment for industries/technologies
  3. Competitor mentions and pain points
  4. Trending topics in relevant subreddits

Data source:
  - PullPush API — free historical full-text search across all of Reddit
    No API key, no Reddit account, no approval process required.

The module is industry-agnostic: it takes the user's search context
(industry, technology, region) and finds relevant Reddit discussions.

Cost: $0 — zero setup, zero credentials
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

# LLM for sentiment analysis (uses whatever's already configured)
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_API_BASE = "https://api.moonshot.ai/v1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# PullPush (free Reddit search — no auth, no approval needed)
PULLPUSH_BASE = "https://api.pullpush.io"

# Subreddit groups by category
SUBREDDIT_GROUPS = {
    "b2b_general": [
        "sales", "b2bmarketing", "leadgeneration", "Entrepreneur",
        "smallbusiness", "startups",
    ],
    "tech": [
        "SaaS", "webdev", "sysadmin", "devops", "ITManagers",
        "programming", "technology",
    ],
    "manufacturing": [
        "manufacturing", "supplychain", "logistics", "engineering",
        "MechanicalEngineering", "CNC",
    ],
    "marketing": [
        "marketing", "digital_marketing", "PPC", "SEO", "socialmedia",
    ],
    "ecommerce": [
        "ecommerce", "FulfillmentByAmazon", "shopify", "dropship",
    ],
    "finance": [
        "fintech", "accounting", "tax", "FinancialPlanning",
    ],
    "general": [
        "AskReddit", "IAmA", "business",
    ],
}

# High-signal buying intent phrases
BUYING_INTENT_PHRASES = [
    "looking for a",
    "recommend a",
    "need help with",
    "best tool for",
    "switching from",
    "alternative to",
    "anyone use",
    "vendor for",
    "supplier for",
    "agency for",
    "platform for",
    "solution for",
    "who do you use for",
    "can anyone suggest",
    "shopping for",
    "in the market for",
]


# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────

@dataclass
class RedditPost:
    """A single Reddit post/comment with metadata."""
    title: str
    body: str
    subreddit: str
    score: int
    num_comments: int
    url: str
    author: str
    created_utc: float
    post_type: str = "submission"  # "submission" or "comment"
    
    @property
    def created_date(self) -> str:
        return datetime.fromtimestamp(self.created_utc, tz=timezone.utc).strftime("%Y-%m-%d")
    
    @property
    def age_days(self) -> int:
        return int((time.time() - self.created_utc) / 86400)
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body[:500],  # Truncate for API response
            "subreddit": f"r/{self.subreddit}",
            "score": self.score,
            "num_comments": self.num_comments,
            "url": self.url,
            "author": self.author,
            "created_date": self.created_date,
            "age_days": self.age_days,
            "post_type": self.post_type,
        }


@dataclass
class RedditSignal:
    """An analyzed Reddit signal with sentiment and classification."""
    post: RedditPost
    signal_type: str  # "buying_intent", "pain_point", "competitor_mention", "industry_trend", "discussion"
    sentiment: str    # "positive", "negative", "neutral", "frustrated"
    relevance_score: float  # 0-1
    summary: str = ""
    key_phrases: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            **self.post.to_dict(),
            "signal_type": self.signal_type,
            "sentiment": self.sentiment,
            "relevance_score": self.relevance_score,
            "summary": self.summary,
            "key_phrases": self.key_phrases,
        }


@dataclass
class RedditPulse:
    """Aggregated market pulse from Reddit signals."""
    query: str
    subreddits_searched: list[str]
    total_posts_found: int
    signals: list[RedditSignal]
    sentiment_breakdown: dict = field(default_factory=dict)
    top_themes: list[str] = field(default_factory=list)
    buying_intent_count: int = 0
    market_summary: str = ""
    searched_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "subreddits_searched": self.subreddits_searched,
            "total_posts_found": self.total_posts_found,
            "signals": [s.to_dict() for s in self.signals[:25]],  # Top 25
            "sentiment_breakdown": self.sentiment_breakdown,
            "top_themes": self.top_themes,
            "buying_intent_count": self.buying_intent_count,
            "market_summary": self.market_summary,
            "searched_at": self.searched_at,
        }


# ──────────────────────────────────────────────
# PullPush Client (free, no auth, no approval)
# ──────────────────────────────────────────────

class PullPushClient:
    """Search historical Reddit data via PullPush API (free, no auth)."""
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
    
    async def search_submissions(
        self,
        query: str,
        subreddit: Optional[str] = None,
        size: int = 25,
        sort: str = "score",
    ) -> list[RedditPost]:
        """Search Reddit submissions via PullPush."""
        await self._ensure_client()
        
        # NOTE: We intentionally omit the 'after' date filter because
        # PullPush's archive may lag behind the current date by months.
        # Instead we rely on score-based sorting to surface the best content.
        params = {
            "q": query,
            "size": min(size, 100),
            "sort": sort,
            "sort_type": "desc",
        }
        if subreddit:
            params["subreddit"] = subreddit
        
        try:
            resp = await self._client.get(
                f"{PULLPUSH_BASE}/reddit/search/submission/",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("PullPush search failed: %s", e)
            return []
        
        raw_items = data.get("data", [])
        logger.info("PullPush submissions for q=%r → %d results", query, len(raw_items))
        
        posts = []
        for item in raw_items:
            posts.append(RedditPost(
                title=item.get("title", ""),
                body=item.get("selftext", "")[:2000],
                subreddit=item.get("subreddit", ""),
                score=item.get("score", 0),
                num_comments=item.get("num_comments", 0),
                url=f"https://reddit.com{item.get('permalink', '')}",
                author=item.get("author", "[deleted]"),
                created_utc=item.get("created_utc", 0),
                post_type="submission",
            ))
        
        return posts
    
    async def search_comments(
        self,
        query: str,
        subreddit: Optional[str] = None,
        size: int = 25,
    ) -> list[RedditPost]:
        """Search Reddit comments via PullPush."""
        await self._ensure_client()
        
        params = {
            "q": query,
            "size": min(size, 100),
            "sort": "score",
            "sort_type": "desc",
        }
        if subreddit:
            params["subreddit"] = subreddit
        
        try:
            resp = await self._client.get(
                f"{PULLPUSH_BASE}/reddit/search/comment/",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("PullPush comment search failed: %s", e)
            return []
        
        raw_items = data.get("data", [])
        logger.info("PullPush comments for q=%r → %d results", query, len(raw_items))
        
        posts = []
        for item in raw_items:
            posts.append(RedditPost(
                title="",  # Comments don't have titles
                body=item.get("body", "")[:2000],
                subreddit=item.get("subreddit", ""),
                score=item.get("score", 0),
                num_comments=0,
                url=f"https://reddit.com{item.get('permalink', '')}",
                author=item.get("author", "[deleted]"),
                created_utc=item.get("created_utc", 0),
                post_type="comment",
            ))
        
        return posts
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ──────────────────────────────────────────────
# Sentiment Analyzer (LLM-powered)
# ──────────────────────────────────────────────

class RedditAnalyzer:
    """Analyzes Reddit posts for sentiment, buying intent, and market signals."""
    
    def __init__(self):
        # Use cheapest available LLM
        if KIMI_API_KEY:
            self._client = AsyncOpenAI(api_key=KIMI_API_KEY, base_url=KIMI_API_BASE)
            self._model = "kimi-k2-0711"
        elif OPENAI_API_KEY:
            self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            self._model = "gpt-4o-mini"
        else:
            self._client = None
            self._model = None
    
    async def analyze_posts(
        self,
        posts: list[RedditPost],
        search_context: str,
    ) -> list[RedditSignal]:
        """Classify and score a batch of Reddit posts using LLM."""
        if not posts:
            return []
        
        # If no LLM available, use keyword-based fallback
        if not self._client:
            return self._keyword_fallback(posts, search_context)
        
        # Batch posts into groups of 10 for efficiency
        signals = []
        for i in range(0, len(posts), 10):
            batch = posts[i:i+10]
            batch_signals = await self._analyze_batch(batch, search_context)
            signals.extend(batch_signals)
            # Small delay to avoid rate limits
            if i + 10 < len(posts):
                await asyncio.sleep(1)
        
        return signals
    
    async def _analyze_batch(
        self,
        posts: list[RedditPost],
        search_context: str,
    ) -> list[RedditSignal]:
        """Analyze a batch of posts with a single LLM call."""
        posts_text = ""
        for idx, p in enumerate(posts):
            text = p.title + ("\n" + p.body[:300] if p.body else "")
            posts_text += f"\n[POST {idx}] r/{p.subreddit} (score:{p.score}) — {text.strip()}\n"
        
        prompt = f"""Analyze these Reddit posts for a B2B sales intelligence platform.

SEARCH CONTEXT: {search_context}

POSTS:
{posts_text}

For each post, classify:
1. signal_type: "buying_intent" | "pain_point" | "competitor_mention" | "industry_trend" | "discussion"
2. sentiment: "positive" | "negative" | "neutral" | "frustrated"
3. relevance_score: 0.0-1.0 (how relevant to the search context)
4. summary: one-line summary of why this matters for sales intelligence
5. key_phrases: 2-3 key phrases extracted

Return a JSON array with one object per post, in order:
[{{"post_index": 0, "signal_type": "...", "sentiment": "...", "relevance_score": 0.8, "summary": "...", "key_phrases": ["...", "..."]}}]

Only return the JSON array, no other text."""

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            
            text = resp.choices[0].message.content or ""
            # Extract JSON array
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if not match:
                return self._keyword_fallback(posts, search_context)
            
            results = json.loads(match.group())
            
            signals = []
            for item in results:
                idx = item.get("post_index", 0)
                if 0 <= idx < len(posts):
                    signals.append(RedditSignal(
                        post=posts[idx],
                        signal_type=item.get("signal_type", "discussion"),
                        sentiment=item.get("sentiment", "neutral"),
                        relevance_score=float(item.get("relevance_score", 0.5)),
                        summary=item.get("summary", ""),
                        key_phrases=item.get("key_phrases", []),
                    ))
            
            return signals
            
        except Exception as e:
            logger.warning("LLM analysis failed: %s — falling back to keywords", e)
            return self._keyword_fallback(posts, search_context)
    
    async def generate_market_summary(
        self,
        signals: list[RedditSignal],
        search_context: str,
    ) -> str:
        """Generate a concise market pulse summary from analyzed signals."""
        if not signals or not self._client:
            return self._basic_summary(signals)
        
        # Build signal digest
        digest = ""
        for s in signals[:15]:  # Top 15 most relevant
            digest += f"- [{s.signal_type}] [{s.sentiment}] r/{s.post.subreddit}: {s.summary}\n"
        
        prompt = f"""You are a B2B market analyst. Based on these Reddit signals, write a concise market pulse summary (3-5 sentences) for a sales team.

SEARCH CONTEXT: {search_context}

SIGNALS:
{digest}

Focus on:
1. Overall market sentiment (is the market hot, cold, shifting?)
2. Key pain points buyers are expressing
3. Any emerging trends or opportunities
4. Actionable insight for the sales team

Write naturally, like a market brief. No bullet points."""

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=500,
            )
            return resp.choices[0].message.content or self._basic_summary(signals)
        except Exception:
            return self._basic_summary(signals)
    
    def _keyword_fallback(
        self,
        posts: list[RedditPost],
        search_context: str,
    ) -> list[RedditSignal]:
        """Simple keyword-based classification when no LLM is available."""
        signals = []
        context_lower = search_context.lower()
        
        for post in posts:
            text = (post.title + " " + post.body).lower()
            
            # Detect buying intent
            has_intent = any(phrase in text for phrase in BUYING_INTENT_PHRASES)
            
            # Detect pain points
            pain_words = ["frustrated", "terrible", "worst", "hate", "problem", "issue", "broken", "struggling"]
            has_pain = any(w in text for w in pain_words)
            
            # Detect positive sentiment
            pos_words = ["love", "great", "excellent", "recommend", "best", "amazing", "perfect"]
            has_positive = any(w in text for w in pos_words)
            
            # Simple relevance: how many context words appear in the post
            context_words = [w for w in context_lower.split() if len(w) > 3]
            if context_words:
                relevance = sum(1 for w in context_words if w in text) / len(context_words)
            else:
                relevance = 0.3
            
            if has_intent:
                signal_type = "buying_intent"
            elif has_pain:
                signal_type = "pain_point"
            else:
                signal_type = "discussion"
            
            if has_pain:
                sentiment = "frustrated"
            elif has_positive:
                sentiment = "positive"
            else:
                sentiment = "neutral"
            
            signals.append(RedditSignal(
                post=post,
                signal_type=signal_type,
                sentiment=sentiment,
                relevance_score=min(relevance + (0.3 if has_intent else 0), 1.0),
                summary=post.title[:100] if post.title else post.body[:100],
            ))
        
        return signals
    
    def _basic_summary(self, signals: list[RedditSignal]) -> str:
        """Generate a basic summary without LLM."""
        if not signals:
            return "No relevant Reddit discussions found for this search."
        
        intent_count = sum(1 for s in signals if s.signal_type == "buying_intent")
        pain_count = sum(1 for s in signals if s.signal_type == "pain_point")
        pos_count = sum(1 for s in signals if s.sentiment == "positive")
        neg_count = sum(1 for s in signals if s.sentiment in ("negative", "frustrated"))
        
        parts = [f"Found {len(signals)} relevant Reddit discussions."]
        if intent_count:
            parts.append(f"{intent_count} show buying intent.")
        if pain_count:
            parts.append(f"{pain_count} mention pain points or frustrations.")
        if pos_count > neg_count:
            parts.append("Overall sentiment leans positive.")
        elif neg_count > pos_count:
            parts.append("Overall sentiment leans negative — potential opportunity to solve pain points.")
        
        return " ".join(parts)


# ──────────────────────────────────────────────
# Main orchestrator
# ──────────────────────────────────────────────

class RedditSignalEngine:
    """Orchestrates Reddit data collection (PullPush) and LLM analysis."""
    
    def __init__(self):
        self.pullpush = PullPushClient()
        self.analyzer = RedditAnalyzer()
    
    def _pick_subreddits(self, industry: Optional[str] = None) -> list[str]:
        """Pick relevant subreddits based on the industry."""
        subs = list(SUBREDDIT_GROUPS["b2b_general"])  # Always include B2B
        
        if not industry:
            return subs
        
        industry_lower = industry.lower()
        
        # Map industry keywords to subreddit groups
        mappings = {
            "tech": ["tech", "software", "saas", "it", "cloud", "ai", "data"],
            "manufacturing": ["manufactur", "industrial", "cnc", "machine", "factory", "hardware"],
            "marketing": ["market", "advertis", "brand", "agency", "pr "],
            "ecommerce": ["ecommerce", "e-commerce", "retail", "shop", "store", "amazon"],
            "finance": ["financ", "bank", "insur", "fintech", "account", "invest"],
        }
        
        for group, keywords in mappings.items():
            if any(kw in industry_lower for kw in keywords):
                subs.extend(SUBREDDIT_GROUPS.get(group, []))
        
        return list(set(subs))
    
    def _build_search_queries(
        self,
        industry: Optional[str] = None,
        technology: Optional[str] = None,
        company_profile: Optional[str] = None,
    ) -> list[str]:
        """Build effective search queries from the user's context."""
        queries = []
        
        # Industry-focused queries
        if industry:
            queries.append(industry)
            for phrase in ["looking for", "recommend", "best"]:
                queries.append(f"{phrase} {industry}")
        
        # Technology-focused queries
        if technology:
            queries.append(technology)
            queries.append(f"{technology} recommendation")
        
        # Combined queries
        if industry and technology:
            queries.append(f"{industry} {technology}")
        
        # Company profile queries (e.g., "magnet manufacturer")
        if company_profile:
            queries.append(company_profile)
            queries.append(f"looking for {company_profile}")
        
        return queries[:5]  # Max 5 queries to stay within rate limits
    
    async def get_pulse(
        self,
        industry: Optional[str] = None,
        technology: Optional[str] = None,
        company_profile: Optional[str] = None,
        custom_query: Optional[str] = None,
        time_range: str = "month",
        max_results: int = 50,
    ) -> RedditPulse:
        """Get a market pulse from Reddit for the given search context.
        
        Args:
            industry: Target industry (e.g., "robotics", "SaaS")
            technology: Technology focus (e.g., "brushless motors", "CRM")
            company_profile: What kind of company (e.g., "magnet manufacturer")
            custom_query: Optional freeform search query
            time_range: "day", "week", "month", "year"
            max_results: Maximum posts to collect
        
        Returns:
            RedditPulse with analyzed signals and market summary
        """
        search_context = " | ".join(filter(None, [industry, technology, company_profile, custom_query]))
        if not search_context:
            return RedditPulse(
                query="",
                subreddits_searched=[],
                total_posts_found=0,
                signals=[],
                searched_at=datetime.now(timezone.utc).isoformat(),
            )
        
        # Pick subreddits
        subreddits = self._pick_subreddits(industry)
        
        # Build queries
        queries = self._build_search_queries(industry, technology, company_profile)
        if custom_query:
            queries.insert(0, custom_query)
        
        # Search PullPush — submissions + comments in parallel (free, no auth)
        # NOTE: We don't filter by date because PullPush's archive may not
        # cover recent dates. We return the best-scoring posts instead.
        per_query = max(max_results // max(len(queries), 1), 10)
        
        tasks = []
        for query in queries[:4]:
            tasks.append(self.pullpush.search_submissions(
                query=query,
                size=per_query,
            ))
            tasks.append(self.pullpush.search_comments(
                query=query,
                size=per_query // 2,
            ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_posts: list[RedditPost] = []
        for result in results:
            if isinstance(result, list):
                all_posts.extend(result)
            elif isinstance(result, Exception):
                logger.warning("PullPush fetch error: %s", result)
        
        logger.info("PullPush total raw posts collected: %d", len(all_posts))
        
        # Deduplicate by URL
        seen_urls = set()
        unique_posts = []
        for post in all_posts:
            if post.url not in seen_urls and (post.title or post.body):
                seen_urls.add(post.url)
                unique_posts.append(post)
        
        logger.info("After dedup: %d unique posts", len(unique_posts))
        
        # Sort by score (engagement)
        unique_posts.sort(key=lambda p: p.score, reverse=True)
        unique_posts = unique_posts[:max_results]
        
        # Analyze with LLM
        signals = await self.analyzer.analyze_posts(unique_posts, search_context)
        
        # Sort by relevance
        signals.sort(key=lambda s: s.relevance_score, reverse=True)
        
        # Compute sentiment breakdown
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0, "frustrated": 0}
        signal_type_counts = {"buying_intent": 0, "pain_point": 0, "competitor_mention": 0, "industry_trend": 0, "discussion": 0}
        
        for s in signals:
            sentiment_counts[s.sentiment] = sentiment_counts.get(s.sentiment, 0) + 1
            signal_type_counts[s.signal_type] = signal_type_counts.get(s.signal_type, 0) + 1
        
        # Generate market summary
        market_summary = await self.analyzer.generate_market_summary(signals, search_context)
        
        # Extract top themes from key phrases
        all_phrases = []
        for s in signals:
            all_phrases.extend(s.key_phrases)
        # Count phrase frequency
        phrase_freq = {}
        for p in all_phrases:
            phrase_freq[p.lower()] = phrase_freq.get(p.lower(), 0) + 1
        top_themes = sorted(phrase_freq, key=phrase_freq.get, reverse=True)[:10]
        
        pulse = RedditPulse(
            query=search_context,
            subreddits_searched=subreddits,
            total_posts_found=len(unique_posts),
            signals=signals,
            sentiment_breakdown=sentiment_counts,
            top_themes=top_themes,
            buying_intent_count=signal_type_counts.get("buying_intent", 0),
            market_summary=market_summary,
            searched_at=datetime.now(timezone.utc).isoformat(),
        )
        
        return pulse
    
    async def close(self):
        await self.pullpush.close()


# ──────────────────────────────────────────────
# Module-level convenience
# ──────────────────────────────────────────────

_engine: Optional[RedditSignalEngine] = None


def get_engine() -> RedditSignalEngine:
    """Get or create the singleton Reddit signal engine."""
    global _engine
    if _engine is None:
        _engine = RedditSignalEngine()
    return _engine


async def get_reddit_pulse(
    industry: Optional[str] = None,
    technology: Optional[str] = None,
    company_profile: Optional[str] = None,
    custom_query: Optional[str] = None,
    time_range: str = "month",
) -> dict:
    """Convenience function — returns a dict ready for API response."""
    engine = get_engine()
    pulse = await engine.get_pulse(
        industry=industry,
        technology=technology,
        company_profile=company_profile,
        custom_query=custom_query,
        time_range=time_range,
    )
    return pulse.to_dict()
