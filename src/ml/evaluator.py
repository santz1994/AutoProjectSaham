"""
Model Evaluation Metrics

Comprehensive evaluation beyond simple accuracy:
- ROC-AUC, Precision-Recall curves
- Sharpe ratio of predictions
- Maximum drawdown
- Win rate vs loss rate
- Kelly Criterion optimal sizing
- Confusion matrix analysis

Usage:
    from src.ml.evaluator import ModelEvaluator
    
    evaluator = ModelEvaluator()
    metrics = evaluator.evaluate(y_true, y_pred_proba)
    evaluator.plot_metrics(y_true, y_pred_proba)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from sklearn.metrics import (
    roc_auc_score,
    roc_curve,
    precision_recall_curve,
    average_precision_score,
    confusion_matrix,
    classification_report,
    accuracy_score,
    f1_score
)


@dataclass
class EvaluationMetrics:
    """Container for evaluation metrics."""
    
    # Classification metrics
    accuracy: float
    auc: float
    average_precision: float
    f1_score: float
    
    # Trading metrics
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    loss_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    kelly_fraction: Optional[float] = None
    
    # Confusion matrix
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'classification': {
                'accuracy': self.accuracy,
                'auc': self.auc,
                'average_precision': self.average_precision,
                'f1_score': self.f1_score
            },
            'trading': {
                'sharpe_ratio': self.sharpe_ratio,
                'max_drawdown': self.max_drawdown,
                'win_rate': self.win_rate,
                'loss_rate': self.loss_rate,
                'avg_win': self.avg_win,
                'avg_loss': self.avg_loss,
                'kelly_fraction': self.kelly_fraction
            },
            'confusion_matrix': {
                'true_positives': self.true_positives,
                'false_positives': self.false_positives,
                'true_negatives': self.true_negatives,
                'false_negatives': self.false_negatives
            }
        }


class ModelEvaluator:
    """Comprehensive model evaluation."""
    
    def __init__(self, threshold: float = 0.5):
        """
        Initialize evaluator.
        
        Args:
            threshold: Classification threshold
        """
        self.threshold = threshold
    
    def evaluate(
        self,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        returns: Optional[np.ndarray] = None
    ) -> EvaluationMetrics:
        """
        Comprehensive model evaluation.
        
        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            returns: Actual returns for trading metrics (optional)
            
        Returns:
            EvaluationMetrics instance
        """
        # Convert probabilities to binary predictions
        y_pred = (y_pred_proba >= self.threshold).astype(int)
        
        # Classification metrics
        accuracy = accuracy_score(y_true, y_pred)
        auc = roc_auc_score(y_true, y_pred_proba)
        avg_precision = average_precision_score(y_true, y_pred_proba)
        f1 = f1_score(y_true, y_pred)
        
        # Confusion matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        
        # Initialize trading metrics
        sharpe_ratio = None
        max_drawdown = None
        win_rate = None
        loss_rate = None
        avg_win = None
        avg_loss = None
        kelly_fraction = None
        
        # Calculate trading metrics if returns provided
        if returns is not None:
            trading_metrics = self._calculate_trading_metrics(
                y_true, y_pred, returns
            )
            sharpe_ratio = trading_metrics['sharpe_ratio']
            max_drawdown = trading_metrics['max_drawdown']
            win_rate = trading_metrics['win_rate']
            loss_rate = trading_metrics['loss_rate']
            avg_win = trading_metrics['avg_win']
            avg_loss = trading_metrics['avg_loss']
            kelly_fraction = trading_metrics['kelly_fraction']
        
        return EvaluationMetrics(
            accuracy=accuracy,
            auc=auc,
            average_precision=avg_precision,
            f1_score=f1,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            kelly_fraction=kelly_fraction,
            true_positives=int(tp),
            false_positives=int(fp),
            true_negatives=int(tn),
            false_negatives=int(fn)
        )
    
    def _calculate_trading_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        returns: np.ndarray
    ) -> Dict:
        """
        Calculate trading-specific metrics.
        
        Args:
            y_true: True labels
            y_pred: Predicted labels
            returns: Actual returns
            
        Returns:
            Dictionary of trading metrics
        """
        # Strategy returns (only trade when predicted positive)
        strategy_returns = np.where(y_pred == 1, returns, 0)
        
        # Sharpe ratio
        if len(strategy_returns) > 0 and strategy_returns.std() > 0:
            sharpe_ratio = np.mean(strategy_returns) / strategy_returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # Maximum drawdown
        cumulative_returns = np.cumsum(strategy_returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = cumulative_returns - running_max
        max_drawdown = float(drawdown.min())
        
        # Win/loss analysis
        trades = strategy_returns[strategy_returns != 0]
        winning_trades = trades[trades > 0]
        losing_trades = trades[trades < 0]
        
        total_trades = len(trades)
        
        if total_trades > 0:
            win_rate = len(winning_trades) / total_trades
            loss_rate = len(losing_trades) / total_trades
            avg_win = winning_trades.mean() if len(winning_trades) > 0 else 0.0
            avg_loss = abs(losing_trades.mean()) if len(losing_trades) > 0 else 0.0
        else:
            win_rate = 0.0
            loss_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
        
        # Kelly Criterion
        if loss_rate > 0 and avg_loss > 0:
            kelly_fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
            kelly_fraction = max(0, min(kelly_fraction, 1))  # Clamp to [0, 1]
        else:
            kelly_fraction = 0.0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'loss_rate': loss_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'kelly_fraction': kelly_fraction
        }
    
    def print_report(self, metrics: EvaluationMetrics) -> None:
        """
        Print formatted evaluation report.
        
        Args:
            metrics: EvaluationMetrics instance
        """
        print("\n" + "="*60)
        print("MODEL EVALUATION REPORT".center(60))
        print("="*60 + "\n")
        
        # Classification metrics
        print("📊 Classification Metrics:")
        print(f"  Accuracy:           {metrics.accuracy:.4f}")
        print(f"  ROC-AUC:            {metrics.auc:.4f}")
        print(f"  Average Precision:  {metrics.average_precision:.4f}")
        print(f"  F1 Score:           {metrics.f1_score:.4f}")
        
        # Confusion matrix
        print(f"\n📋 Confusion Matrix:")
        print(f"  True Positives:     {metrics.true_positives}")
        print(f"  False Positives:    {metrics.false_positives}")
        print(f"  True Negatives:     {metrics.true_negatives}")
        print(f"  False Negatives:    {metrics.false_negatives}")
        
        # Trading metrics
        if metrics.sharpe_ratio is not None:
            print(f"\n💰 Trading Metrics:")
            print(f"  Sharpe Ratio:       {metrics.sharpe_ratio:.4f}")
            print(f"  Max Drawdown:       {metrics.max_drawdown:.4f}")
            print(f"  Win Rate:           {metrics.win_rate:.2%}")
            print(f"  Loss Rate:          {metrics.loss_rate:.2%}")
            print(f"  Avg Win:            {metrics.avg_win:.4f}")
            print(f"  Avg Loss:           {metrics.avg_loss:.4f}")
            print(f"  Kelly Fraction:     {metrics.kelly_fraction:.4f}")
        
        print("\n" + "="*60 + "\n")
    
    def compare_models(
        self,
        models_dict: Dict[str, Tuple[np.ndarray, np.ndarray]],
        y_true: np.ndarray,
        returns: Optional[np.ndarray] = None
    ) -> pd.DataFrame:
        """
        Compare multiple models.
        
        Args:
            models_dict: Dict of {model_name: (y_pred_proba, y_pred)}
            y_true: True labels
            returns: Actual returns (optional)
            
        Returns:
            DataFrame with comparison
        """
        results = []
        
        for model_name, (y_pred_proba, _) in models_dict.items():
            metrics = self.evaluate(y_true, y_pred_proba, returns)
            
            result = {
                'Model': model_name,
                'Accuracy': metrics.accuracy,
                'AUC': metrics.auc,
                'F1': metrics.f1_score,
            }
            
            if metrics.sharpe_ratio is not None:
                result.update({
                    'Sharpe': metrics.sharpe_ratio,
                    'Max DD': metrics.max_drawdown,
                    'Win Rate': metrics.win_rate
                })
            
            results.append(result)
        
        df = pd.DataFrame(results)
        return df.sort_values('AUC', ascending=False)


def calculate_prediction_confidence(y_pred_proba: np.ndarray) -> Dict:
    """
    Calculate prediction confidence statistics.
    
    Args:
        y_pred_proba: Predicted probabilities
        
    Returns:
        Dictionary with confidence statistics
    """
    # Distance from decision boundary (0.5)
    confidence = np.abs(y_pred_proba - 0.5)
    
    return {
        'mean_confidence': float(confidence.mean()),
        'median_confidence': float(np.median(confidence)),
        'high_confidence_pct': float((confidence > 0.3).mean()),  # >80% or <20%
        'low_confidence_pct': float((confidence < 0.1).mean())    # 40-60%
    }


def statistical_significance_test(
    model1_scores: np.ndarray,
    model2_scores: np.ndarray
) -> Dict:
    """
    Test if difference between two models is statistically significant.
    
    Args:
        model1_scores: Scores from model 1
        model2_scores: Scores from model 2
        
    Returns:
        Dictionary with test results
    """
    from scipy import stats
    
    # Paired t-test
    t_stat, p_value = stats.ttest_rel(model1_scores, model2_scores)
    
    mean_diff = model1_scores.mean() - model2_scores.mean()
    
    return {
        't_statistic': float(t_stat),
        'p_value': float(p_value),
        'mean_difference': float(mean_diff),
        'significant': p_value < 0.05
    }


# Example usage
if __name__ == "__main__":
    # Generate synthetic data
    np.random.seed(42)
    n_samples = 1000
    
    y_true = np.random.randint(0, 2, n_samples)
    y_pred_proba = np.random.beta(2, 2, n_samples)  # Probabilities
    returns = np.random.normal(0.001, 0.02, n_samples) * (2 * y_true - 1)  # Correlated returns
    
    # Evaluate
    evaluator = ModelEvaluator()
    metrics = evaluator.evaluate(y_true, y_pred_proba, returns)
    
    # Print report
    evaluator.print_report(metrics)
    
    # Confidence analysis
    confidence_stats = calculate_prediction_confidence(y_pred_proba)
    print("📈 Prediction Confidence:")
    for key, value in confidence_stats.items():
        print(f"  {key}: {value:.4f}")
    
    print("\n✓ Evaluation complete")
