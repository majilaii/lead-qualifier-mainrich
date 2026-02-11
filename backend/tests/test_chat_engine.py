"""
Tests for chat_engine.py

Verifies API key filtering (the fixed locals() bug), data classes,
and readiness extraction.
"""

import os
import pytest


def test_placeholder_key_detection():
    """Verify _is_placeholder correctly identifies fake keys."""
    from chat_engine import _is_placeholder

    assert _is_placeholder("sk-your-api-key-here") is True
    assert _is_placeholder("your_key") is True
    assert _is_placeholder("changeme") is True
    assert _is_placeholder("sk-real1234abcd") is False
    assert _is_placeholder("") is False


def test_readiness_to_dict():
    from chat_engine import Readiness

    r = Readiness(industry=True, company_profile=False, technology_focus=True)
    d = r.to_dict()
    assert d["industry"] is True
    assert d["companyProfile"] is False
    assert d["technologyFocus"] is True
    assert d["isReady"] is False


def test_extracted_context_dataclass():
    from chat_engine import ExtractedContext

    ctx = ExtractedContext(
        industry="Manufacturing",
        company_profile="SMBs making EVs",
        technology_focus="battery tech",
    )
    assert ctx.industry == "Manufacturing"
    assert ctx.qualifying_criteria is None
