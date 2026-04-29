"""Async MIMO LLM Connector for AI-driven Sentiment Analysis.

Uses OpenRouter API with MIMO-v2.5-Pro model to generate sentiment scores
for financial news and market data. Returns structured sentiment vectors
suitable for RL observation augmentation.

Wajib menggunakan httpx (async) agar pemanggilan API model yang berat ini
tidak memblokir event loop di src/api/server.py.

Environment variables:
    MIMO_API_KEY or OPENROUTER_API_KEY: API key for OpenRouter
    MIMO_MODEL_ID: Model identifier (default: mimoai/mimo-v2.5-pro)
    MIMO_BASE_URL: API base URL (default: https://openrouter.ai/api/v1)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------
_DEFAULT_MODEL_ID = "mimoai/mimo-v2.5-pro"
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_TIMEOUT = 60.0  # seconds
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 2.0  # seconds between retries
_SENTIMENT_PROMPT_TEMPLATE = (
    "You are a financial sentiment analyst. Analyze the following market news/data "
    "and return a JSON object with exactly these fields:\n"
    "  \"sentiment_score\": float between -1.0 (extremely bearish) and 1.0 (extremely bullish),\n"
    "  \"confidence\": float between 0.0 and 1.0,\n"
    "  \"key_factors\": list of up to 5 short strings describing the main drivers,\n"
    "  \"risk_level\": one of \"low\", \"medium\", \"high\", \"extreme\",\n"
    "  \"market_regime_hint\": one of \"trending_up\", \"trending_down\", \"ranging\", \"volatile\"\n\n"
    "Market context: {market_context}\n\n"
    "News/Data to analyze:\n{news_text}\n\n"
    "Respond ONLY with the JSON object, no other text."
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SentimentResult:
    """Structured sentiment output from MIMO LLM."""
    sentiment_score: float = 0.0          # -1.0 (bearish) to 1.0 (bullish)
    confidence: float = 0.0               # 0.0 to 1.0
    key_factors: List[str] = field(default_factory=list)
    risk_level: str = "medium"            # low / medium / high / extreme
    market_regime_hint: str = "ranging"   # trending_up / trending_down / ranging / volatile
    raw_response: str = ""
    model_id: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment_score": self.sentiment_score,
            "confidence": self.confidence,
            "key_factors": self.key_factors,
            "risk_level": self.risk_level,
            "market_regime_hint": self.market_regime_hint,
            "model_id": self.model_id,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "error": self.error,
        }

    def to_vector(self) -> List[float]:
        """Convert to a numeric vector for RL observation augmentation.

        Returns 7 floats:
            [0] sentiment_score  (-1..1)
            [1] confidence       (0..1)
            [2] risk_level_encoded (0..1)
            [3] regime_trending_up (0 or 1)
            [4] regime_trending_down (0 or 1)
            [5] regime_ranging (0 or 1)
            [6] regime_volatile (0 or 1)
        """
        risk_map = {"low": 0.15, "medium": 0.45, "high": 0.75, "extreme": 1.0}
        regime_map = {
            "trending_up": [1.0, 0.0, 0.0, 0.0],
            "trending_down": [0.0, 1.0, 0.0, 0.0],
            "ranging": [0.0, 0.0, 1.0, 0.0],
            "volatile": [0.0, 0.0, 0.0, 1.0],
        }
        return [
            float(self.sentiment_score),
            float(self.confidence),
            risk_map.get(self.risk_level, 0.5),
            *regime_map.get(self.market_regime_hint, [0.0, 0.0, 1.0, 0.0]),
        ]


# ---------------------------------------------------------------------------
# Async connector
# ---------------------------------------------------------------------------
class MimoLLMConnector:
    """Async connector for MIMO-v2.5-Pro via OpenRouter API.

    Uses httpx.AsyncClient so API calls never block the FastAPI event loop.
    Supports retries, exponential backoff, and structured output parsing.

    Usage::

        connector = MimoLLMConnector()
        result = await connector.analyze_sentiment("Bitcoin surges 10%...")
        vector = result.to_vector()  # for RL observation
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_delay: float = _DEFAULT_RETRY_DELAY,
        market_context: str = "Global crypto/forex market, 24/7 trading",
    ):
        self.api_key = api_key or os.getenv("MIMO_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
        self.model_id = model_id or os.getenv("MIMO_MODEL_ID", _DEFAULT_MODEL_ID)
        self.base_url = (base_url or os.getenv("MIMO_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.retry_delay = float(retry_delay)
        self.market_context = market_context

        self._client: Optional[Any] = None  # httpx.AsyncClient (lazy)
        self._request_count: int = 0
        self._error_count: int = 0

    # ---- lifecycle ----

    async def _get_client(self):  # type: ignore[return]
        """Lazily create httpx.AsyncClient (avoids import issues if httpx missing)."""
        if self._client is None:
            try:
                import httpx
            except ImportError:
                raise RuntimeError(
                    "httpx is required for MimoLLMConnector. "
                    "Install with: pip install httpx"
                )
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://autosaham.local",
                    "X-Title": "AutoSaham AI Sentiment",
                },
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Gracefully close the HTTP client."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ---- core API ----

    async def analyze_sentiment(
        self,
        news_text: str,
        market_context: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> SentimentResult:
        """Analyze financial news text and return structured sentiment.

        Args:
            news_text: News headline(s) and/or article text to analyze.
            market_context: Override default market context string.
            temperature: LLM temperature (lower = more deterministic).
            max_tokens: Max tokens in completion.

        Returns:
            SentimentResult with parsed scores.
        """
        if not self.api_key:
            return SentimentResult(
                error="No API key configured. Set MIMO_API_KEY or OPENROUTER_API_KEY.",
            )

        prompt = _SENTIMENT_PROMPT_TEMPLATE.format(
            market_context=market_context or self.market_context,
            news_text=news_text[:4000],  # truncate to avoid token overflow
        )

        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": "You are a precise financial sentiment analysis AI. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        t0 = time.monotonic()
        result = SentimentResult(model_id=self.model_id)

        for attempt in range(1, self.max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post("/chat/completions", json=payload)
                self._request_count += 1

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", self.retry_delay * attempt))
                    logger.warning("MIMO API rate-limited (attempt %d/%d), retry in %.1fs", attempt, self.max_retries, retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Extract content from OpenRouter/OpenAI-style response
                content = ""
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")

                result.raw_response = content
                result.latency_ms = (time.monotonic() - t0) * 1000

                # Parse structured JSON from LLM response
                parsed = self._parse_sentiment_json(content)
                result.sentiment_score = parsed.get("sentiment_score", 0.0)
                result.confidence = parsed.get("confidence", 0.0)
                result.key_factors = parsed.get("key_factors", [])
                result.risk_level = parsed.get("risk_level", "medium")
                result.market_regime_hint = parsed.get("market_regime_hint", "ranging")

                # Clamp values to valid ranges
                result.sentiment_score = max(-1.0, min(1.0, result.sentiment_score))
                result.confidence = max(0.0, min(1.0, result.confidence))

                logger.info(
                    "MIMO sentiment: score=%.3f conf=%.3f risk=%s regime=%s (%.0fms)",
                    result.sentiment_score, result.confidence,
                    result.risk_level, result.market_regime_hint,
                    result.latency_ms,
                )
                return result

            except Exception as e:
                self._error_count += 1
                logger.warning("MIMO API call failed (attempt %d/%d): %s", attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * attempt)
                else:
                    result.error = str(e)
                    result.latency_ms = (time.monotonic() - t0) * 1000

        return result

    async def analyze_batch(
        self,
        news_items: List[str],
        market_context: Optional[str] = None,
    ) -> SentimentResult:
        """Analyze multiple news items in a single prompt and return aggregated sentiment.

        Args:
            news_items: List of news headlines/texts.
            market_context: Override default market context.

        Returns:
            Aggregated SentimentResult.
        """
        combined = "\n---\n".join(
            f"[{i+1}] {item[:800]}" for i, item in enumerate(news_items[:20])
        )
        return await self.analyze_sentiment(combined, market_context=market_context)

    # ---- internal helpers ----

    @staticmethod
    def _parse_sentiment_json(raw: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

        logger.warning("Failed to parse MIMO JSON response, using defaults")
        return {}

    # ---- stats ----

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "base_url": self.base_url,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "has_api_key": bool(self.api_key),
        }


# ---------------------------------------------------------------------------
# Synchronous wrapper (for use in non-async contexts like scheduler threads)
# ---------------------------------------------------------------------------

def analyze_sentiment_sync(
    news_text: str,
    api_key: Optional[str] = None,
    model_id: Optional[str] = None,
    market_context: str = "Global crypto/forex market, 24/7 trading",
) -> SentimentResult:
    """Synchronous wrapper around MimoLLMConnector for use in scheduler threads.

    Creates a new event loop if none is running.
    """
    async def _run():
        async with MimoLLMConnector(
            api_key=api_key, model_id=model_id, market_context=market_context
        ) as connector:
            return await connector.analyze_sentiment(news_text)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context but called synchronously —
        # this should not happen in normal use; fallback to thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, _run()).result()
    else:
        return asyncio.run(_run())