"""
Web Scraper Module — crawl4ai + Playwright (with httpx fallback)

Visits company websites using a headless Chromium browser and extracts:
  - Full page content as clean Markdown (for LLM text analysis)
  - Screenshot as base64 JPEG (for LLM vision analysis)

Falls back to httpx + html2text if crawl4ai can't be imported (e.g. on
Python 3.9 where crawl4ai ≥0.6 uses X|None syntax requiring 3.10+).

Key functions:
  - crawl_company(url)  → CrawlResult with markdown + screenshot
  - batch_crawl(urls)   → Crawl multiple URLs with concurrency control
  - truncate_to_tokens() → Trim content to stay within LLM token limits
  - resize_screenshot()  → Compress screenshots to save vision API costs
"""

import asyncio
import base64
from io import BytesIO
from typing import Optional
import logging
import time
import re

import httpx

from models import CrawlResult
from config import (
    SCREENSHOT_WIDTH, 
    SCREENSHOT_HEIGHT, 
    REQUEST_TIMEOUT,
    MAX_TOKENS_INPUT
)

logger = logging.getLogger(__name__)

# ── Try importing crawl4ai (requires Python 3.10+) ──────────────
_HAS_CRAWL4AI = False
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from PIL import Image
    _HAS_CRAWL4AI = True
    logger.info("crawl4ai loaded — using Playwright browser-based crawling")
except Exception as _import_err:
    logger.warning("crawl4ai not available (%s) — falling back to httpx text-only crawling", _import_err)
    # Stubs so the rest of the module can reference these names
    AsyncWebCrawler = None  # type: ignore
    BrowserConfig = None  # type: ignore
    CrawlerRunConfig = None  # type: ignore
    CacheMode = None  # type: ignore
    Image = None  # type: ignore


# Default browser config (shared across the module) — only if crawl4ai available
_DEFAULT_BROWSER_CONFIG = (
    BrowserConfig(
        headless=True,
        viewport_width=SCREENSHOT_WIDTH,
        viewport_height=SCREENSHOT_HEIGHT,
    )
    if _HAS_CRAWL4AI
    else None
)


class CrawlerPool:
    """
    Manages a shared browser instance so we don't launch/kill Chromium 
    for every single URL. This alone cuts crawl time by ~60%.

    When crawl4ai is not available (Python 3.9), degrades to httpx-based
    fetching — no screenshots, but text content is still extracted.
    
    Usage:
        async with CrawlerPool() as pool:
            result = await pool.crawl(url)
    """
    
    def __init__(self, browser_config=None):
        self._browser_config = browser_config or _DEFAULT_BROWSER_CONFIG
        self._crawler = None
        self._httpx_client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        if _HAS_CRAWL4AI:
            self._crawler = AsyncWebCrawler(config=self._browser_config)
            await self._crawler.__aenter__()
        else:
            self._httpx_client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self
    
    async def __aexit__(self, *args):
        if self._crawler:
            await self._crawler.__aexit__(*args)
            self._crawler = None
        if self._httpx_client:
            await self._httpx_client.aclose()
            self._httpx_client = None
    
    async def crawl(self, url: str, take_screenshot: bool = True) -> CrawlResult:
        """Crawl a single URL using the shared browser (or httpx fallback)."""
        if _HAS_CRAWL4AI and self._crawler:
            return await _do_crawl(url, take_screenshot, self._crawler)
        else:
            return await _do_crawl_httpx(url, self._httpx_client)


async def _do_crawl(
    url: str, 
    take_screenshot: bool, 
    crawler: AsyncWebCrawler,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> CrawlResult:
    """Internal: execute a crawl with exponential-backoff retries."""
    start_time = time.time()
    
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=REQUEST_TIMEOUT * 1000,
        wait_until="domcontentloaded",
        screenshot=take_screenshot,
        remove_overlay_elements=True,
        exclude_external_links=True,
    )

    last_error: str = ""

    for attempt in range(1, max_retries + 1):
        try:
            result = await crawler.arun(url=url, config=crawler_config)
            
            if not result.success:
                last_error = f"Crawl failed: {result.error_message or 'Unknown error'}"
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.debug("Retry %d/%d for %s in %.1fs -- %s", attempt, max_retries, url, delay, last_error)
                    await asyncio.sleep(delay)
                    continue
                return CrawlResult(
                    url=url,
                    success=False,
                    error_message=last_error,
                    crawl_time_seconds=time.time() - start_time,
                )
            
            markdown_content = str(result.markdown) if result.markdown else ""
            markdown_content = truncate_to_tokens(markdown_content, MAX_TOKENS_INPUT)
            
            screenshot_base64 = None
            if take_screenshot and result.screenshot:
                screenshot_base64 = resize_screenshot(result.screenshot)
            
            title = None
            if result.metadata and isinstance(result.metadata, dict):
                title = result.metadata.get('title')
            
            return CrawlResult(
                url=url,
                success=True,
                markdown_content=markdown_content,
                screenshot_base64=screenshot_base64,
                title=title,
                crawl_time_seconds=time.time() - start_time,
            )
            
        except asyncio.TimeoutError:
            last_error = "Timeout: Page took too long to load"
        except Exception as e:
            last_error = f"Exception: {str(e)[:200]}"

        if attempt < max_retries:
            delay = base_delay * (2 ** (attempt - 1))
            logger.debug("Retry %d/%d for %s in %.1fs -- %s", attempt, max_retries, url, delay, last_error)
            await asyncio.sleep(delay)

    return CrawlResult(
        url=url,
        success=False,
        error_message=f"Failed after {max_retries} attempts: {last_error}",
        crawl_time_seconds=time.time() - start_time,
    )


# ── httpx fallback (Python 3.9 / no Playwright) ──────────────────

def _html_to_markdown(html: str) -> str:
    """Rough HTML→text conversion using regex. No external deps needed."""
    # Remove script/style blocks
    text = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
    # Replace common block elements with newlines
    text = re.sub(r'<(br|hr|/p|/div|/h[1-6]|/li|/tr)[^>]*>', '\n', text, flags=re.I)
    # Replace headings with markdown-style
    text = re.sub(r'<h([1-6])[^>]*>(.*?)</h\1>', lambda m: '#' * int(m.group(1)) + ' ' + m.group(2), text, flags=re.S | re.I)
    # Replace list items
    text = re.sub(r'<li[^>]*>', '- ', text, flags=re.I)
    # Replace links: <a href="url">text</a> → [text](url)
    text = re.sub(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.S | re.I)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def _do_crawl_httpx(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> CrawlResult:
    """Fallback crawl using httpx when crawl4ai is unavailable.
    
    No screenshots (requires browser), but extracts text content via
    regex-based HTML→markdown. Good enough for LLM text qualification.
    """
    start_time = time.time()

    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    last_error = ""
    try:
        for attempt in range(1, max_retries + 1):
            try:
                resp = await client.get(url)
                resp.raise_for_status()

                html = resp.text
                markdown_content = _html_to_markdown(html)
                markdown_content = truncate_to_tokens(markdown_content, MAX_TOKENS_INPUT)

                # Extract <title>
                title = None
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
                if title_match:
                    title = title_match.group(1).strip()

                return CrawlResult(
                    url=url,
                    success=True,
                    markdown_content=markdown_content,
                    screenshot_base64=None,  # No screenshots in httpx mode
                    title=title,
                    crawl_time_seconds=time.time() - start_time,
                )
            except httpx.TimeoutException:
                last_error = "Timeout: Page took too long to respond"
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
            except Exception as e:
                last_error = f"Exception: {str(e)[:200]}"

            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.debug("httpx retry %d/%d for %s in %.1fs -- %s", attempt, max_retries, url, delay, last_error)
                await asyncio.sleep(delay)

        return CrawlResult(
            url=url,
            success=False,
            error_message=f"Failed after {max_retries} attempts: {last_error}",
            crawl_time_seconds=time.time() - start_time,
        )
    finally:
        if own_client:
            await client.aclose()


async def crawl_company(url: str, take_screenshot: bool = True, crawler_pool: 'CrawlerPool' = None) -> CrawlResult:
    """
    Crawl a company website and extract content.
    
    Args:
        url: Website URL to crawl
        take_screenshot: Whether to capture a screenshot for vision analysis
        crawler_pool: Optional shared CrawlerPool (avoids launching new browser).
                      If None, launches a temporary browser for this one crawl.
        
    Returns:
        CrawlResult with markdown content and optional screenshot
    """
    # If a shared pool is provided, use it (fast path)
    if crawler_pool is not None:
        return await crawler_pool.crawl(url, take_screenshot)
    
    # Otherwise, launch a one-off browser (slow path — used for standalone calls)
    async with CrawlerPool() as pool:
        return await pool.crawl(url, take_screenshot)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncate text to approximately max_tokens.
    Uses rough estimate of 4 chars per token.
    """
    # Rough estimate: 1 token ≈ 4 characters
    max_chars = max_tokens * 4
    
    if len(text) <= max_chars:
        return text
    
    # Truncate and add indicator
    truncated = text[:max_chars]
    
    # Try to break at a sentence boundary
    last_period = truncated.rfind('.')
    if last_period > max_chars * 0.8:  # Only if we don't lose too much
        truncated = truncated[:last_period + 1]
    
    return truncated + "\n\n[Content truncated for processing...]"


def resize_screenshot(screenshot_base64: str, target_width: int = 720) -> str:
    """
    Resize screenshot to reduce size for vision API.
    Converts to JPEG and resizes to target width.
    """
    if Image is None:
        return screenshot_base64  # PIL not available — return as-is
    try:
        # Decode base64
        image_data = base64.b64decode(screenshot_base64)
        image = Image.open(BytesIO(image_data))
        
        # Calculate new height maintaining aspect ratio
        aspect_ratio = image.height / image.width
        target_height = int(target_width * aspect_ratio)
        
        # Resize
        image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (for JPEG)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        # Save as JPEG with moderate quality
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=75, optimize=True)
        
        # Re-encode to base64
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
        
    except Exception as e:
        logger.warning("Could not resize screenshot: %s", e)
        return screenshot_base64  # Return original if resize fails


async def batch_crawl(urls: list[str], concurrency: int = 5, take_screenshot: bool = True) -> list[CrawlResult]:
    """
    Crawl multiple URLs in parallel using a shared browser.
    Much faster than calling crawl_company() in a loop.
    """
    semaphore = asyncio.Semaphore(concurrency)
    
    async def crawl_with_semaphore(pool: CrawlerPool, url: str) -> CrawlResult:
        async with semaphore:
            return await pool.crawl(url, take_screenshot)
    
    async with CrawlerPool() as pool:
        tasks = [crawl_with_semaphore(pool, url) for url in urls]
        return await asyncio.gather(*tasks)


# Simple test
if __name__ == "__main__":
    async def test():
        result = await crawl_company("https://www.bostondynamics.com")
        print(f"Success: {result.success}")
        print(f"Title: {result.title}")
        print(f"Content length: {len(result.markdown_content or '')} chars")
        print(f"Has screenshot: {result.screenshot_base64 is not None}")
        print(f"Time: {result.crawl_time_seconds:.2f}s")
    
    asyncio.run(test())
