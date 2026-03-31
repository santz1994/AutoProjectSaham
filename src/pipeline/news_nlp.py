"""NLP utilities for IDX announcements using transformers (IndoBERT).

This module provides a small wrapper around `transformers.pipeline` that can
be used to score sentiment for Indonesian corporate action documents.
"""
from __future__ import annotations

from typing import Dict

try:
    from transformers import pipeline
except Exception:
    pipeline = None


class IDXInformationExtractor:
    def __init__(self, model: str = "indobenchmark/indobert-base-p1", device: int = -1):
        if pipeline is None:
            raise RuntimeError("transformers pipeline not available; install transformers")
        # device=-1 runs on CPU; set to 0 if a GPU is available
        self.nlp_pipeline = pipeline("sentiment-analysis", model=model, device=device)

    def analyze_corporate_action(self, text_document: str) -> Dict:
        """
        Analyze a document (string) and return an average sentiment score and a simple signal.
        """
        # split into roughly 512-char chunks (tokenization may differ per model)
        max_chunk = 512
        chunks = [text_document[i : i + max_chunk] for i in range(0, len(text_document), max_chunk)]

        sentiment_scores = []
        for chunk in chunks:
            result = self.nlp_pipeline(chunk)[0]
            label = result.get('label', '').lower()
            score = float(result.get('score', 0.0))
            if label.startswith('positive'):
                sentiment_scores.append(score)
            elif label.startswith('negative'):
                sentiment_scores.append(-score)
            else:
                sentiment_scores.append(0.0)

        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

        signal = 'NEUTRAL'
        if avg_sentiment > 0.3:
            signal = 'BULLISH'
        elif avg_sentiment < -0.3:
            signal = 'BEARISH'

        return {'sentiment_score': float(avg_sentiment), 'signal': signal}
