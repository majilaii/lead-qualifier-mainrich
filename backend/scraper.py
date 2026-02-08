"""
Web Scraper Module — crawl4ai + Playwright

Visits company websites using a headless Chromium browser and extracts:
  - Full page content as clean Markdown (for LLM text analysis)
  - Screenshot as base64 JPEG (for LLM vision analysis)

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
import time

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from PIL import Image

from models import CrawlResult
from config import (
    SCREENSHOT_WIDTH, 
    SCREENSHOT_HEIGHT, 
    REQUEST_TIMEOUT,
    MAX_TOKENS_INPUT
)


# Default browser config (shared across the module)
_DEFAULT_BROWSER_CONFIG = BrowserConfig(
    headless=True,
    viewport_width=SCREENSHOT_WIDTH,
    viewport_height=SCREENSHOT_HEIGHT,
)


class CrawlerPool:
    """
    Manages a shared browser instance so we don't launch/kill Chromium 
    for every single URL. This alone cuts crawl time by ~60%.
    
    Usage:
        async with CrawlerPool() as pool:
            result = await pool.crawl(url)
    """
    
    def __init__(self, browser_config: BrowserConfig = None):
        self._browser_config = browser_config or _DEFAULT_BROWSER_CONFIG
        self._crawler: AsyncWebCrawler = None
    
    async def __aenter__(self):
        self._crawler = AsyncWebCrawler(config=self._browser_config)
        await self._crawler.__aenter__()
        return self
    
    async def __aexit__(self, *args):
        if self._crawler:
            await self._crawler.__aexit__(*args)
            self._crawler = None
    
    async def crawl(self, url: str, take_screenshot: bool = True) -> CrawlResult:
        """Crawl a single URL using the shared browser."""
        return await _do_crawl(url, take_screenshot, self._crawler)


async def _do_crawl(
    url: str, 
    take_screenshot: bool, 
    crawler: AsyncWebCrawler
) -> CrawlResult:
    """Internal: execute a crawl on a given crawler instance."""
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
    
    try:
        result = await crawler.arun(url=url, config=crawler_config)
        
        if not result.success:
            return CrawlResult(
                url=url,
                success=False,
                error_message=f"Crawl failed: {result.error_message or 'Unknown error'}",
                crawl_time_seconds=time.time() - start_time
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
            crawl_time_seconds=time.time() - start_time
        )
        
    except asyncio.TimeoutError:
        return CrawlResult(
            url=url,
            success=False,
            error_message="Timeout: Page took too long to load",
            crawl_time_seconds=time.time() - start_time
        )
    except Exception as e:
        return CrawlResult(
            url=url,
            success=False,
            error_message=f"Exception: {str(e)[:200]}",
            crawl_time_seconds=time.time() - start_time
        )


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
        print(f"Warning: Could not resize screenshot: {e}")
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
