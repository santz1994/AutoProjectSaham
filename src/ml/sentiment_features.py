"""
News Sentiment Features for ML Models

Converts news articles into actionable machine learning features:
1. Sentiment scores (VADER for general, FinBERT for financial)
2. News volume metrics
3. Temporal decay weighting
4. Entity extraction and topic classification

These features capture market sentiment and information flow,
which are strong predictors of short-term price movements.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import numpy as np
import pandas as pd

# VADER for general sentiment (lightweight, no GPU needed)
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    SentimentIntensityAnalyzer = None

# FinBERT for financial sentiment (more accurate but heavier)
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    pipeline = None


class SentimentAnalyzer:
    """
    Multi-model sentiment analyzer combining VADER and FinBERT.
    
    VADER: Fast, rule-based, good for general text
    FinBERT: Transformer-based, specialized for financial news
    """
    
    def __init__(
        self, 
        use_vader: bool = True, 
        use_finbert: bool = False,
        finbert_model: str = "ProsusAI/finbert",
        device: int = -1
    ):
        """
        Initialize sentiment analyzer.
        
        Args:
            use_vader: Enable VADER sentiment analysis
            use_finbert: Enable FinBERT sentiment analysis (slower but more accurate)
            finbert_model: HuggingFace model name for financial sentiment
            device: -1 for CPU, 0+ for GPU
        """
        self.use_vader = use_vader
        self.use_finbert = use_finbert
        
        # Initialize VADER
        if use_vader:
            if not VADER_AVAILABLE:
                raise ImportError("vaderSentiment not installed. Run: pip install vaderSentiment")
            self.vader = SentimentIntensityAnalyzer()
        else:
            self.vader = None
        
        # Initialize FinBERT
        if use_finbert:
            if not TRANSFORMERS_AVAILABLE:
                raise ImportError("transformers not installed. Run: pip install transformers")
            try:
                self.finbert = pipeline(
                    "sentiment-analysis",
                    model=finbert_model,
                    device=device,
                    max_length=512,
                    truncation=True
                )
            except Exception as e:
                print(f"Warning: FinBERT initialization failed: {e}")
                self.finbert = None
                self.use_finbert = False
        else:
            self.finbert = None
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of a single text.
        
        Args:
            text: Input text (news article, headline, etc.)
            
        Returns:
            Dictionary with sentiment scores:
            - vader_compound: VADER compound score (-1 to 1)
            - finbert_score: FinBERT score (-1 to 1)
            - combined_score: Average of available scores
        """
        results = {}
        
        # VADER analysis
        if self.use_vader and self.vader:
            vader_scores = self.vader.polarity_scores(text)
            results['vader_compound'] = vader_scores['compound']
            results['vader_positive'] = vader_scores['pos']
            results['vader_negative'] = vader_scores['neg']
            results['vader_neutral'] = vader_scores['neu']
        
        # FinBERT analysis
        if self.use_finbert and self.finbert:
            try:
                finbert_result = self.finbert(text[:512])[0]  # Limit to 512 chars
                label = finbert_result['label'].lower()
                score = finbert_result['score']
                
                # Convert to -1 to 1 scale
                if 'positive' in label:
                    results['finbert_score'] = score
                elif 'negative' in label:
                    results['finbert_score'] = -score
                else:
                    results['finbert_score'] = 0.0
            except Exception as e:
                print(f"FinBERT analysis failed: {e}")
                results['finbert_score'] = 0.0
        
        # Combined score (average of available models)
        scores = []
        if 'vader_compound' in results:
            scores.append(results['vader_compound'])
        if 'finbert_score' in results:
            scores.append(results['finbert_score'])
        
        results['combined_score'] = np.mean(scores) if scores else 0.0
        
        return results
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """
        Analyze sentiment for multiple texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of sentiment dictionaries
        """
        return [self.analyze_text(text) for text in texts]


class NewsFeatureExtractor:
    """
    Extract ML features from news articles for a given symbol.
    
    Features include:
    - Sentiment scores over multiple time windows (1d, 7d, 30d)
    - News volume (article count)
    - Negative news ratio
    - Sentiment volatility
    - Temporal decay weighting (recent news more important)
    """
    
    def __init__(
        self, 
        sentiment_analyzer: Optional[SentimentAnalyzer] = None,
        cache_enabled: bool = True
    ):
        """
        Initialize feature extractor.
        
        Args:
            sentiment_analyzer: SentimentAnalyzer instance (creates default if None)
            cache_enabled: Enable sentiment score caching
        """
        if sentiment_analyzer is None:
            # Default: use VADER only (fast, no GPU needed)
            self.sentiment_analyzer = SentimentAnalyzer(use_vader=True, use_finbert=False)
        else:
            self.sentiment_analyzer = sentiment_analyzer
        
        self.cache_enabled = cache_enabled
        self._sentiment_cache = {}  # Cache: text -> sentiment scores
    
    def _get_sentiment(self, text: str) -> Dict[str, float]:
        """Get sentiment with caching."""
        if self.cache_enabled:
            # Use text hash as cache key
            text_key = hash(text)
            if text_key not in self._sentiment_cache:
                self._sentiment_cache[text_key] = self.sentiment_analyzer.analyze_text(text)
            return self._sentiment_cache[text_key]
        else:
            return self.sentiment_analyzer.analyze_text(text)
    
    def extract_features(
        self, 
        articles: List[Dict],
        symbol: str,
        current_date: datetime,
        windows: List[int] = [1, 7, 30]
    ) -> Dict[str, float]:
        """
        Extract features from news articles for a symbol.
        
        Args:
            articles: List of article dicts with keys: 'title', 'content', 'publishedAt', 'symbol'
            symbol: Target stock symbol
            current_date: Reference date for feature extraction
            windows: Time windows in days (e.g., [1, 7, 30] for 1-day, 7-day, 30-day)
            
        Returns:
            Dictionary of features:
            - news_sentiment_1d: Avg sentiment in last 1 day
            - news_volume_1d: Article count in last 1 day
            - news_sentiment_7d: Avg sentiment in last 7 days
            - news_volume_7d: Article count in last 7 days
            - negative_news_ratio_7d: Ratio of negative articles
            - sentiment_volatility_7d: Std dev of sentiment scores
            - news_sentiment_30d: Avg sentiment in last 30 days
        """
        features = {}
        
        # Filter articles for this symbol
        symbol_articles = [
            art for art in articles 
            if art.get('symbol') == symbol or symbol in art.get('title', '') or symbol in art.get('content', '')
        ]
        
        for window_days in windows:
            cutoff_date = current_date - timedelta(days=window_days)
            
            # Filter articles within time window
            window_articles = [
                art for art in symbol_articles
                if self._parse_date(art.get('publishedAt')) >= cutoff_date
            ]
            
            if not window_articles:
                # No articles in this window
                features[f'news_sentiment_{window_days}d'] = 0.0
                features[f'news_volume_{window_days}d'] = 0
                if window_days == 7:
                    features['negative_news_ratio_7d'] = 0.0
                    features['sentiment_volatility_7d'] = 0.0
                continue
            
            # Extract sentiments with temporal decay
            sentiments = []
            weights = []
            negative_count = 0
            
            for art in window_articles:
                # Combine title and content
                text = f"{art.get('title', '')} {art.get('content', '')}"
                sentiment = self._get_sentiment(text)
                
                # Temporal decay weight (recent articles more important)
                article_date = self._parse_date(art.get('publishedAt'))
                days_ago = (current_date - article_date).days
                weight = np.exp(-0.1 * days_ago)  # Exponential decay
                
                sentiments.append(sentiment['combined_score'])
                weights.append(weight)
                
                if sentiment['combined_score'] < -0.2:
                    negative_count += 1
            
            # Weighted average sentiment
            weighted_sentiment = np.average(sentiments, weights=weights)
            features[f'news_sentiment_{window_days}d'] = float(weighted_sentiment)
            features[f'news_volume_{window_days}d'] = len(window_articles)
            
            # Additional features for 7-day window
            if window_days == 7:
                features['negative_news_ratio_7d'] = negative_count / len(window_articles)
                features['sentiment_volatility_7d'] = float(np.std(sentiments))
        
        return features
    
    def _parse_date(self, date_str: Optional[str]) -> datetime:
        """Parse date string to datetime object."""
        if date_str is None:
            return datetime.now()
        
        # Try common formats
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Fallback: return current time
        return datetime.now()
    
    def clear_cache(self):
        """Clear sentiment cache."""
        self._sentiment_cache.clear()


class EntityExtractor:
    """
    Extract named entities and topics from news text.
    
    Identifies:
    - Company names (stock symbols)
    - Event types (earnings, merger, regulation)
    - Key financial terms
    """
    
    # Financial event keywords
    EVENT_KEYWORDS = {
        'earnings': ['earnings', 'profit', 'revenue', 'quarterly', 'annual report'],
        'merger': ['merger', 'acquisition', 'takeover', 'buyout', 'M&A'],
        'regulation': ['regulation', 'policy', 'government', 'law', 'compliance'],
        'expansion': ['expansion', 'growth', 'new market', 'investment'],
        'crisis': ['loss', 'decline', 'crisis', 'scandal', 'investigation']
    }
    
    def extract_events(self, text: str) -> Dict[str, bool]:
        """
        Extract event types mentioned in text.
        
        Args:
            text: News article text
            
        Returns:
            Dictionary of event types: {event_type: is_mentioned}
        """
        text_lower = text.lower()
        
        events = {}
        for event_type, keywords in self.EVENT_KEYWORDS.items():
            mentioned = any(keyword in text_lower for keyword in keywords)
            events[f'event_{event_type}'] = mentioned
        
        return events
    
    def extract_symbols(self, text: str) -> List[str]:
        """
        Extract stock symbols from text.
        
        Args:
            text: News article text
            
        Returns:
            List of detected symbols (e.g., ['BBCA', 'TLKM'])
        """
        # Pattern: 4 uppercase letters (IDX symbols)
        pattern = r'\b[A-Z]{4}\b'
        symbols = re.findall(pattern, text)
        
        return list(set(symbols))  # Remove duplicates


def create_sentiment_features_for_dataset(
    dataset_df: pd.DataFrame,
    news_articles: List[Dict],
    output_csv: Optional[str] = None
) -> pd.DataFrame:
    """
    Add sentiment features to existing dataset.
    
    Args:
        dataset_df: DataFrame with columns ['symbol', 't_index', ...]
        news_articles: List of news article dicts
        output_csv: Optional path to save enhanced dataset
        
    Returns:
        Enhanced DataFrame with sentiment features
    """
    print("Adding sentiment features to dataset...")
    
    # Initialize feature extractor
    extractor = NewsFeatureExtractor()
    
    # Add sentiment features row by row
    sentiment_features_list = []
    
    for idx, row in dataset_df.iterrows():
        symbol = row['symbol']
        # Use t_index as proxy for date (or use actual date if available)
        current_date = datetime.now() - timedelta(days=len(dataset_df) - idx)
        
        features = extractor.extract_features(
            news_articles,
            symbol,
            current_date,
            windows=[1, 7, 30]
        )
        
        sentiment_features_list.append(features)
        
        if idx % 100 == 0:
            print(f"Processed {idx}/{len(dataset_df)} rows...")
    
    # Convert to DataFrame and merge
    sentiment_df = pd.DataFrame(sentiment_features_list)
    enhanced_df = pd.concat([dataset_df, sentiment_df], axis=1)
    
    if output_csv:
        enhanced_df.to_csv(output_csv, index=False)
        print(f"Saved enhanced dataset to {output_csv}")
    
    return enhanced_df


if __name__ == "__main__":
    # Example usage
    print("=== News Sentiment Features Example ===\n")
    
    # Initialize sentiment analyzer
    analyzer = SentimentAnalyzer(use_vader=True, use_finbert=False)
    
    # Test texts
    texts = [
        "BBCA posts record quarterly profit, beating analyst expectations",
        "TLKM faces regulatory challenges as government reviews pricing policy",
        "Market remains neutral amid mixed economic signals"
    ]
    
    print("Sentiment Analysis:")
    for text in texts:
        result = analyzer.analyze_text(text)
        print(f"\nText: {text}")
        print(f"  VADER Compound: {result.get('vader_compound', 'N/A'):.3f}")
        print(f"  Combined Score: {result['combined_score']:.3f}")
    
    # Feature extraction example
    print("\n\n=== Feature Extraction Example ===\n")
    
    # Mock news articles
    articles = [
        {
            'symbol': 'BBCA',
            'title': 'BCA reports strong earnings growth',
            'content': 'Bank Central Asia reported 15% profit growth in Q3.',
            'publishedAt': '2024-03-25T10:00:00Z'
        },
        {
            'symbol': 'BBCA',
            'title': 'Analysts upgrade BCA rating',
            'content': 'Leading analysts upgraded BBCA to buy rating.',
            'publishedAt': '2024-03-26T14:30:00Z'
        },
        {
            'symbol': 'TLKM',
            'title': 'Telkom faces pressure from competition',
            'content': 'Telkom Indonesia experiencing margin pressure.',
            'publishedAt': '2024-03-20T09:00:00Z'
        }
    ]
    
    extractor = NewsFeatureExtractor(sentiment_analyzer=analyzer)
    
    features = extractor.extract_features(
        articles,
        symbol='BBCA',
        current_date=datetime(2024, 3, 27),
        windows=[1, 7, 30]
    )
    
    print("Features for BBCA:")
    for key, value in features.items():
        print(f"  {key}: {value}")
    
    # Entity extraction
    print("\n\n=== Entity Extraction Example ===\n")
    
    entity_extractor = EntityExtractor()
    
    text = "BBCA announces merger with regional bank, expects earnings boost"
    events = entity_extractor.extract_events(text)
    symbols = entity_extractor.extract_symbols(text)
    
    print(f"Text: {text}")
    print(f"Detected events: {[k for k, v in events.items() if v]}")
    print(f"Detected symbols: {symbols}")
