"""
Tests for reddit_signals.py

Covers data-class construction, subreddit groups, buying intent phrases,
and PullPushClient basics.
"""

import time
import pytest
from unittest.mock import patch

from reddit_signals import (
    RedditPost,
    RedditSignal,
    RedditPulse,
    PullPushClient,
    SUBREDDIT_GROUPS,
    BUYING_INTENT_PHRASES,
)


# ═══════════════════════════════════════════════
# SUBREDDIT_GROUPS structure
# ═══════════════════════════════════════════════

class TestSubredditGroups:
    def test_all_groups_non_empty(self):
        for group, subs in SUBREDDIT_GROUPS.items():
            assert isinstance(subs, list), f"Group {group} is not a list"
            assert len(subs) > 0, f"Group {group} is empty"

    def test_expected_categories(self):
        expected = {"b2b_general", "tech", "manufacturing", "marketing"}
        assert expected.issubset(set(SUBREDDIT_GROUPS.keys()))

    def test_no_duplicate_subreddits_within_group(self):
        for group, subs in SUBREDDIT_GROUPS.items():
            assert len(subs) == len(set(subs)), f"Duplicate in {group}"


# ═══════════════════════════════════════════════
# BUYING_INTENT_PHRASES
# ═══════════════════════════════════════════════

class TestBuyingIntentPhrases:
    def test_is_non_empty(self):
        assert len(BUYING_INTENT_PHRASES) > 5

    def test_all_lowercase(self):
        for phrase in BUYING_INTENT_PHRASES:
            assert phrase == phrase.lower(), f"'{phrase}' should be lowercase"

    def test_contains_common_phrases(self):
        joined = " ".join(BUYING_INTENT_PHRASES)
        assert "looking for" in joined
        assert "recommend" in joined
        assert "alternative to" in joined


# ═══════════════════════════════════════════════
# RedditPost
# ═══════════════════════════════════════════════

class TestRedditPost:
    def _make_post(self, **kw):
        defaults = {
            "title": "Need a supplier for CNC parts",
            "body": "We're looking for a reliable CNC supplier in the US.",
            "subreddit": "manufacturing",
            "score": 42,
            "num_comments": 12,
            "url": "https://reddit.com/r/manufacturing/abc",
            "author": "testuser",
            "created_utc": time.time() - 86400,  # 1 day ago
        }
        defaults.update(kw)
        return RedditPost(**defaults)

    def test_defaults(self):
        p = self._make_post()
        assert p.post_type == "submission"

    def test_created_date_format(self):
        p = self._make_post(created_utc=1700000000.0)
        assert "-" in p.created_date  # e.g. "2023-11-14"
        assert len(p.created_date) == 10

    def test_age_days(self):
        # Post from ~1 day ago
        p = self._make_post(created_utc=time.time() - 86400)
        assert p.age_days in (0, 1, 2)  # May be 0 or 1 depending on rounding

    def test_to_dict(self):
        p = self._make_post()
        d = p.to_dict()
        assert d["title"] == p.title
        assert d["subreddit"] == f"r/{p.subreddit}"
        assert "score" in d
        assert "age_days" in d
        assert "post_type" in d

    def test_body_truncated_in_dict(self):
        long_body = "x" * 1000
        p = self._make_post(body=long_body)
        d = p.to_dict()
        assert len(d["body"]) <= 500

    def test_comment_type(self):
        p = self._make_post(post_type="comment")
        assert p.post_type == "comment"


# ═══════════════════════════════════════════════
# RedditSignal
# ═══════════════════════════════════════════════

class TestRedditSignal:
    def test_construction(self):
        post = RedditPost(
            title="T", body="B", subreddit="s", score=1,
            num_comments=0, url="u", author="a", created_utc=time.time(),
        )
        sig = RedditSignal(
            post=post,
            signal_type="buying_intent",
            sentiment="frustrated",
            relevance_score=0.9,
            summary="Wants a new tool",
            key_phrases=["looking for", "supplier"],
        )
        assert sig.signal_type == "buying_intent"
        assert sig.relevance_score == 0.9

    def test_to_dict_merges_post(self):
        post = RedditPost(
            title="T", body="B", subreddit="s", score=1,
            num_comments=0, url="u", author="a", created_utc=time.time(),
        )
        sig = RedditSignal(
            post=post, signal_type="pain_point",
            sentiment="negative", relevance_score=0.5,
        )
        d = sig.to_dict()
        assert "title" in d  # from post
        assert "signal_type" in d  # from signal
        assert "sentiment" in d


# ═══════════════════════════════════════════════
# RedditPulse
# ═══════════════════════════════════════════════

class TestRedditPulse:
    def test_construction(self):
        pulse = RedditPulse(
            query="CNC suppliers",
            subreddits_searched=["manufacturing", "CNC"],
            total_posts_found=50,
            signals=[],
            buying_intent_count=5,
            market_summary="Strong demand for CNC parts",
        )
        assert pulse.query == "CNC suppliers"
        assert pulse.total_posts_found == 50

    def test_to_dict(self):
        pulse = RedditPulse(
            query="Q",
            subreddits_searched=["s1"],
            total_posts_found=10,
            signals=[],
        )
        d = pulse.to_dict()
        assert d["query"] == "Q"
        assert d["total_posts_found"] == 10
        assert d["signals"] == []

    def test_signals_truncated_to_25(self):
        post = RedditPost(
            title="T", body="B", subreddit="s", score=1,
            num_comments=0, url="u", author="a", created_utc=time.time(),
        )
        signals = [
            RedditSignal(post=post, signal_type="discussion",
                         sentiment="neutral", relevance_score=0.1)
            for _ in range(30)
        ]
        pulse = RedditPulse(
            query="Q", subreddits_searched=[], total_posts_found=30,
            signals=signals,
        )
        d = pulse.to_dict()
        assert len(d["signals"]) == 25


# ═══════════════════════════════════════════════
# PullPushClient
# ═══════════════════════════════════════════════

class TestPullPushClient:
    def test_init(self):
        client = PullPushClient()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_ensure_client_creates_httpx(self):
        client = PullPushClient()
        await client._ensure_client()
        assert client._client is not None
        # Cleanup
        await client._client.aclose()
