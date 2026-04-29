"""NLP utilities for IDX announcements and news sentiment analysis.

Provides sentiment analysis for Indonesian corporate action documents
and general financial news using:
1. IndoBERT for Indonesian text
2. VADER for general sentiment
3. FinBERT for financial news (English)

Integrated with src.ml.sentiment_features for ML feature extraction.
"""
from __future__ import annotations

from typing import Dict

try:
    from transformers import pipeline
except Exception:
    pipeline = None

# Import sentiment features for integration
try:
    from src.ml.sentiment_features import (
        SentimentAnalyzer,
        NewsFeatureExtractor,
        EntityExtractor
    )
    SENTIMENT_FEATURES_AVAILABLE = True
except Exception:
    SENTIMENT_FEATURES_AVAILABLE = False
    SentimentAnalyzer = None
    NewsFeatureExtractor = None
    EntityExtractor = None


class IDXInformationExtractor:
    def __init__(self, model: str = "indobenchmark/indobert-base-p1", device: int = -1):
        if pipeline is None:
            raise RuntimeError(
                "transformers pipeline not available; install transformers"
            )
        # device=-1 runs on CPU; set to 0 if a GPU is available
        self.nlp_pipeline = pipeline("sentiment-analysis", model=model, device=device)

    def analyze_corporate_action(self, text_document: str) -> Dict:
        """
        Analyze a document (string) and return an average sentiment score
        and a simple signal.
        """
        # split into roughly 512-char chunks (tokenization may differ per model)
        max_chunk = 512
        chunks = [
            text_document[i : i + max_chunk]
            for i in range(0, len(text_document), max_chunk)
        ]

        sentiment_scores = []
        for chunk in chunks:
            result = self.nlp_pipeline(chunk)[0]
            label = result.get("label", "").lower()
            score = float(result.get("score", 0.0))
            if label.startswith("positive"):
                sentiment_scores.append(score)
            elif label.startswith("negative"):
                sentiment_scores.append(-score)
            else:
                sentiment_scores.append(0.0)

        avg_sentiment = (
            sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
        )

        signal = "NEUTRAL"
        if avg_sentiment > 0.3:
            signal = "BULLISH"
        elif avg_sentiment < -0.3:
            signal = "BEARISH"

        return {"sentiment_score": float(avg_sentiment), "signal": signal}


def get_sentiment_analyzer(use_vader: bool = True, use_finbert: bool = False) -> 'SentimentAnalyzer':
    """
    Get a SentimentAnalyzer instance for general use.
    
    Args:
        use_vader: Enable VADER sentiment (fast, good for general text)
        use_finbert: Enable FinBERT (slower, better for financial news)
        
    Returns:
        SentimentAnalyzer instance
        
    Raises:
        ImportError: If sentiment_features module not available
    """
    if not SENTIMENT_FEATURES_AVAILABLE:
        raise ImportError(
            "sentiment_features not available. "
            "Ensure src.ml.sentiment_features is properly installed."
        )
    
    return SentimentAnalyzer(use_vader=use_vader, use_finbert=use_finbert)


def analyze_news_sentiment(text: str) -> Dict[str, float]:
    """
    Quick sentiment analysis for a single news article.
    
    Args:
        text: News article text (title + content)
        
    Returns:
        Dictionary with sentiment scores
    """
    if not SENTIMENT_FEATURES_AVAILABLE:
        # Fallback to basic analysis if sentiment_features not available
        return {"sentiment_score": 0.0, "signal": "NEUTRAL"}
    
    analyzer = get_sentiment_analyzer(use_vader=True, use_finbert=False)
    return analyzer.analyze_text(text)

