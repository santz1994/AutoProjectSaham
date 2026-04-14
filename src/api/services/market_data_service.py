"""Market symbol normalization and news aggregation helpers for API routes."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from src.api.config.frontend_constants import (
    crypto_symbols,
    market_aliases,
    market_news_fallback,
)
from src.api.services.projection_response_service import keyword_sentiment_score

_global_news_cache: Dict[str, Any] = {
    "key": None,
    "fetched_at": None,
    "items": [],
}


def symbol_base(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith("=X"):
        return normalized.replace("=X", "")
    if "-USD" in normalized:
        return normalized.split("-USD")[0]
    return normalized


def symbol_aliases(symbol: str) -> List[str]:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return []

    aliases = {normalized}
    base = symbol_base(normalized)
    if base:
        aliases.add(base)

    if normalized.endswith("=X"):
        pair = normalized.replace("=X", "")
        aliases.add(pair)
        if len(pair) == 6:
            aliases.add(f"{pair[:3]}/{pair[3:]}")
    elif len(normalized) == 6 and normalized.isalpha():
        aliases.add(f"{normalized}=X")
        aliases.add(f"{normalized[:3]}/{normalized[3:]}")

    if "-USD" in normalized:
        base_coin = normalized.split("-USD")[0]
        aliases.add(base_coin)
        aliases.add(f"{base_coin}USDT")
    elif normalized.endswith("USDT") and len(normalized) > 4:
        base_coin = normalized[:-4]
        aliases.add(base_coin)
        aliases.add(f"{base_coin}-USD")

    return list(aliases)


def symbols_match(left: str, right: str) -> bool:
    left_aliases = set(symbol_aliases(left))
    right_aliases = set(symbol_aliases(right))
    if not left_aliases or not right_aliases:
        return False
    return not left_aliases.isdisjoint(right_aliases)


def detect_market_from_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return "unknown"
    if ("." in normalized) and (not normalized.endswith("=X")):
        return "stocks"
    if normalized.startswith("^"):
        return "index"
    if normalized.endswith("=X") or (len(normalized) == 6 and normalized.isalpha()) or "/" in normalized:
        return "forex"
    if "-USD" in normalized or normalized.endswith("USDT"):
        return "crypto"
    return "unknown"


def is_forex_symbol(symbol: str) -> bool:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return False

    if normalized.endswith("=X"):
        pair = normalized[:-2]
        return len(pair) == 6 and pair.isalpha()

    if "/" in normalized:
        compact = normalized.replace("/", "")
        return len(compact) == 6 and compact.isalpha()

    return len(normalized) == 6 and normalized.isalpha()


def is_crypto_symbol(symbol: str) -> bool:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return False

    known_bases = {
        str(item).upper().split("-USD", 1)[0]
        for item in crypto_symbols
        if "-USD" in str(item).upper()
    }

    if "-USD" in normalized:
        base = normalized.split("-USD", 1)[0]
        return bool(base) and (base in known_bases or len(base) >= 2)

    if normalized.endswith("USDT") and len(normalized) > 4:
        base = normalized[:-4]
        return bool(base) and (base in known_bases or len(base) >= 2)

    return False


def is_supported_market_symbol(symbol: str, market: str) -> bool:
    normalized_market = market_aliases.get(str(market or "").strip().lower())
    if normalized_market is None:
        return False

    if normalized_market == "forex":
        return is_forex_symbol(symbol)
    if normalized_market == "crypto":
        return is_crypto_symbol(symbol)
    if normalized_market == "all":
        return is_forex_symbol(symbol) or is_crypto_symbol(symbol)
    return False


def normalize_market_input(market: Optional[str], default: str = "forex") -> str:
    normalized = str(default if market is None else market).strip().lower()
    mapped = market_aliases.get(normalized)
    if mapped is not None:
        return mapped

    fallback = market_aliases.get(str(default).strip().lower())
    return fallback or "forex"


def normalize_market_input_strict(
    market: Optional[str],
    *,
    allow_all: bool = True,
) -> str:
    normalized = market_aliases.get(str(market or "").strip().lower())
    if normalized is None:
        allowed = "forex, crypto, all" if allow_all else "forex, crypto"
        raise HTTPException(
            status_code=400,
            detail=f"market must be one of: {allowed}",
        )
    if (not allow_all) and normalized == "all":
        raise HTTPException(
            status_code=400,
            detail="market must be one of: forex, crypto",
        )
    return normalized


def normalize_symbol_input(symbol: str, market: Optional[str] = None) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return normalized

    normalized_market = (
        normalize_market_input(market)
        if market is not None
        else detect_market_from_symbol(normalized)
    )

    if normalized_market == "forex":
        compact = normalized.replace("/", "")
        if compact.endswith("=X"):
            return compact
        if len(compact) == 6 and compact.isalpha():
            return f"{compact}=X"
        return compact

    if normalized_market == "crypto":
        if normalized.endswith("USDT") and "-" not in normalized:
            return f"{normalized[:-4]}-USD"
        if normalized.endswith("USD") and "-" not in normalized and len(normalized) > 3:
            return f"{normalized[:-3]}-USD"
        if "-" not in normalized:
            return f"{normalized}-USD"
        return normalized

    if normalized.startswith("^"):
        return normalized

    return normalized


def normalize_news_item(raw_item: Dict[str, Any], source_name: str) -> Optional[Dict[str, Any]]:
    title = str(raw_item.get("title") or raw_item.get("headline") or "").strip()
    if not title:
        return None

    published_at = (
        raw_item.get("publishedAt")
        or raw_item.get("published_at")
        or raw_item.get("providerPublishTime")
    )
    if isinstance(published_at, (int, float)):
        published_iso = datetime.fromtimestamp(float(published_at)).isoformat()
    else:
        published_iso = str(published_at or datetime.now().isoformat())

    score = keyword_sentiment_score(title)
    sentiment = "neutral"
    if score > 0.15:
        sentiment = "positive"
    elif score < -0.15:
        sentiment = "negative"

    source = raw_item.get("source")
    if isinstance(source, dict):
        source = source.get("name")

    return {
        "headline": title,
        "sentiment": sentiment,
        "score": round(score, 4),
        "source": str(source or source_name),
        "timestamp": published_iso,
        "url": raw_item.get("url") or raw_item.get("link") or "",
    }


def fetch_global_market_news(limit: int = 10, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(100, int(limit)))
    symbol_key = symbol_base(symbol or "") or "GLOBAL"
    cache_key = f"{symbol_key}:{safe_limit}"

    fetched_at = _global_news_cache.get("fetched_at")
    if (
        _global_news_cache.get("key") == cache_key
        and isinstance(fetched_at, datetime)
        and (datetime.now() - fetched_at).total_seconds() <= 90
    ):
        cached = _global_news_cache.get("items") or []
        return list(cached)[:safe_limit]

    news_items: List[Dict[str, Any]] = []
    seen_headlines = set()

    def _append_items(items: List[Dict[str, Any]], source_name: str) -> None:
        for raw_item in items:
            normalized = normalize_news_item(raw_item, source_name)
            if not normalized:
                continue
            key = normalized["headline"].lower()
            if key in seen_headlines:
                continue
            seen_headlines.add(key)
            news_items.append(normalized)
            if len(news_items) >= safe_limit:
                return

    api_key = os.getenv("NEWSAPI_KEY", "").strip()
    if api_key:
        try:
            from src.pipeline.data_connectors.news_connector import fetch_news

            symbol_key = symbol_base(symbol or "")
            query = "forex OR FX OR USD OR EUR OR bitcoin OR ethereum OR crypto OR Federal Reserve OR CPI OR oil"
            if symbol_key:
                query = f"({symbol_key}) OR ({query})"

            payload = fetch_news(
                query=query,
                api_key=api_key,
                page=1,
                page_size=min(50, safe_limit),
            )
            api_articles = payload.get("articles") if isinstance(payload, dict) else []
            if isinstance(api_articles, list):
                _append_items(api_articles, "NewsAPI")
        except Exception:
            pass

    if len(news_items) < safe_limit:
        try:
            import yfinance as yf

            symbols_to_fetch = []
            if symbol:
                symbols_to_fetch.append(normalize_symbol_input(symbol))
            for item in market_news_fallback:
                if item not in symbols_to_fetch:
                    symbols_to_fetch.append(item)

            for ticker_symbol in symbols_to_fetch:
                ticker = yf.Ticker(ticker_symbol)
                articles = getattr(ticker, "news", None) or []
                if isinstance(articles, list):
                    _append_items(articles, f"yfinance:{ticker_symbol}")
                if len(news_items) >= safe_limit:
                    break
        except Exception:
            pass

    news_items.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    output = news_items[:safe_limit]
    _global_news_cache.update(
        {
            "key": cache_key,
            "fetched_at": datetime.now(),
            "items": output,
        }
    )
    return output
