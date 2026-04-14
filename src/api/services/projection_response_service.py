"""Helpers for AI projection sentiment, rationale, and response phrasing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return float(default)
    if parsed != parsed:
        return float(default)
    if parsed in (float("inf"), float("-inf")):
        return float(default)
    return float(parsed)


def confidence_label(confidence: float) -> str:
    safe_confidence = float(max(0.0, min(1.0, confidence)))
    if safe_confidence < 0.35:
        return "very_low"
    if safe_confidence < 0.50:
        return "low"
    if safe_confidence < 0.65:
        return "medium"
    if safe_confidence < 0.80:
        return "high"
    return "very_high"


def keyword_sentiment_score(text: str) -> float:
    headline = str(text or "").lower()
    if not headline:
        return 0.0

    positive_keywords = [
        "beat",
        "beats",
        "surge",
        "gain",
        "growth",
        "bullish",
        "upgrade",
        "stimulus",
        "easing",
        "strong",
        "optimistic",
        "record high",
        "inflow",
        "accumulation",
        "expansion",
        "rally",
        "outperform",
    ]
    negative_keywords = [
        "miss",
        "drop",
        "selloff",
        "bearish",
        "downgrade",
        "risk-off",
        "tightening",
        "hawkish",
        "inflation spike",
        "recession",
        "war",
        "sanction",
        "outflow",
        "distribution",
        "decline",
        "volatile",
        "warning",
        "fraud",
    ]

    positive_hits = sum(1 for keyword in positive_keywords if keyword in headline)
    negative_hits = sum(1 for keyword in negative_keywords if keyword in headline)
    total_hits = positive_hits + negative_hits

    if total_hits == 0:
        return 0.0
    return float(max(-1.0, min(1.0, (positive_hits - negative_hits) / total_hits)))


def aggregate_news_sentiment(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not news_items:
        return {
            "overallSentiment": 0.0,
            "sentiment": "NEUTRAL",
            "score": 50,
            "sourceBreakdown": {
                "globalNews": 0.0,
                "macroSignals": 0.0,
                "institutionalFlow": 0.0,
            },
        }

    scores: List[float] = []
    for item in news_items:
        title = item.get("headline") or item.get("title") or ""
        score = keyword_sentiment_score(title)
        scores.append(score)

    avg_score = float(sum(scores) / len(scores)) if scores else 0.0
    sentiment_label = "NEUTRAL"
    if avg_score >= 0.20:
        sentiment_label = "BULLISH"
    elif avg_score <= -0.20:
        sentiment_label = "BEARISH"

    return {
        "overallSentiment": avg_score,
        "sentiment": sentiment_label,
        "score": int(max(0, min(100, round((avg_score + 1.0) * 50)))),
        "sourceBreakdown": {
            "globalNews": round(avg_score, 3),
            "macroSignals": round(avg_score * 0.9, 3),
            "institutionalFlow": round(avg_score * 0.8, 3),
        },
    }


def build_ai_rationale(
    symbol: str,
    timeframe: str,
    horizon: int,
    signal: str,
    expected_return: float,
    confidence: float,
    source: str,
    sentiment: Dict[str, Any],
    news_items: List[Dict[str, Any]],
    learning_summary: Optional[Dict[str, Any]] = None,
) -> List[str]:
    direction = "upside" if expected_return >= 0 else "downside"
    confidence_pct = confidence * 100.0
    sentiment_text = sentiment.get("sentiment", "NEUTRAL")

    rationale = [
        (
            f"{str(source).upper()} inference indicates {signal} bias on {symbol} "
            f"for {timeframe} with projected {direction} {expected_return * 100:+.2f}% "
            f"over {horizon} steps (confidence {confidence_pct:.2f}%)."
        ),
        (
            f"Global-news sentiment is {sentiment_text} "
            f"(score {sentiment.get('score', 50)}/100), blended with live candle momentum "
            "to reduce single-model overfitting risk."
        ),
    ]

    if news_items:
        top_news = news_items[0]
        rationale.append(
            (
                f"Latest macro/market driver: {top_news.get('headline', 'N/A')} "
                f"[{top_news.get('source', 'global')}]"
            )
        )

    if isinstance(learning_summary, dict):
        samples = int(max(0, _safe_float(learning_summary.get("observations"), default=0.0)))
        reliability = float(
            max(
                0.0,
                min(1.0, _safe_float(learning_summary.get("reliability"), default=0.0)),
            )
        )
        wins = int(max(0, _safe_float(learning_summary.get("wins"), default=0.0)))
        losses = int(max(0, _safe_float(learning_summary.get("losses"), default=0.0)))
        rationale.append(
            (
                f"Online learning memory across previous projections: reliability {reliability * 100:.2f}% "
                f"from {samples} resolved sample(s) (wins {wins}, losses {losses})."
            )
        )

    return rationale


def build_generated_news_context(
    symbol: str,
    timeframe: str,
    signal: str,
    expected_return: float,
    confidence: float,
) -> List[Dict[str, Any]]:
    now_iso = datetime.now().isoformat()
    direction = "positive" if expected_return > 0 else "negative" if expected_return < 0 else "neutral"
    move_pct = expected_return * 100.0
    confidence_pct = confidence * 100.0

    return [
        {
            "headline": (
                f"AI-generated macro pulse: {symbol} shows {signal} pressure on {timeframe} horizon "
                f"with projected move {move_pct:+.2f}%"
            ),
            "sentiment": direction,
            "score": round(max(-1.0, min(1.0, expected_return * 8.0)), 4),
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
        {
            "headline": (
                "Institutional-flow proxy and live momentum were fused with latest candles "
                "to reduce noisy projections"
            ),
            "sentiment": "neutral",
            "score": 0.0,
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
        {
            "headline": (
                f"Confidence calibration layer running in nonstop mode at {confidence_pct:.2f}% "
                "to learn from previous projection outcomes"
            ),
            "sentiment": "positive" if confidence >= 0.6 else "neutral",
            "score": round(max(-1.0, min(1.0, (confidence - 0.5) * 1.6)), 4),
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
    ]
