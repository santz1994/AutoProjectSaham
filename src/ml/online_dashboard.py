"""
Online Learning Performance Dashboard

Real-time monitoring dashboard for online learning pipeline.
Tracks:
1. Model performance metrics (accuracy, AUC)
2. Concept drift detection events
3. Retraining triggers
4. Feature importance evolution
5. Prediction distribution

Provides both CLI visualization and JSON API for external dashboards.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd


class OnlineLearningDashboard:
    """
    Dashboard for monitoring online learning pipeline.
    
    Collects metrics, detects anomalies, and provides visualization.
    """
    
    def __init__(
        self,
        log_dir: str = "logs/online_learning",
        history_window: int = 1000
    ):
        """
        Initialize dashboard.
        
        Args:
            log_dir: Directory to store dashboard logs
            history_window: Number of recent samples to keep in memory
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.history_window = history_window
        
        # Metrics history
        self.metrics_history: List[Dict] = []
        self.drift_events: List[Dict] = []
        self.retrain_events: List[Dict] = []
        
        # Current session
        self.session_start = datetime.now()
        self.total_predictions = 0
    
    def log_prediction(
        self,
        features: Dict[str, float],
        prediction: int,
        true_label: Optional[int] = None,
        confidence: Optional[float] = None,
        drift_detected: bool = False,
        should_retrain: bool = False,
        performance: Optional[Dict] = None
    ) -> None:
        """
        Log a single prediction event.
        
        Args:
            features: Input features
            prediction: Model prediction
            true_label: Actual label (if available)
            confidence: Prediction confidence
            drift_detected: Whether drift was detected
            should_retrain: Whether retraining was triggered
            performance: Current performance metrics
        """
        self.total_predictions += 1
        
        # Create log entry
        entry = {
            'timestamp': datetime.now().isoformat(),
            'prediction': prediction,
            'true_label': true_label,
            'confidence': confidence,
            'correct': true_label == prediction if true_label is not None else None,
            'drift_detected': drift_detected,
            'should_retrain': should_retrain
        }
        
        if performance:
            entry['accuracy'] = performance.get('accuracy')
            entry['auc'] = performance.get('auc')
            entry['n_samples'] = performance.get('n_samples')
        
        # Add to history (rolling window)
        self.metrics_history.append(entry)
        if len(self.metrics_history) > self.history_window:
            self.metrics_history.pop(0)
        
        # Log drift events
        if drift_detected:
            drift_entry = {
                'timestamp': datetime.now().isoformat(),
                'sample_number': self.total_predictions,
                'accuracy_at_drift': performance.get('accuracy') if performance else None
            }
            self.drift_events.append(drift_entry)
            
            # Save drift event to file
            self._save_event('drift', drift_entry)
        
        # Log retrain events
        if should_retrain:
            retrain_entry = {
                'timestamp': datetime.now().isoformat(),
                'sample_number': self.total_predictions,
                'reason': 'drift' if drift_detected else 'performance',
                'accuracy_before': performance.get('accuracy') if performance else None
            }
            self.retrain_events.append(retrain_entry)
            
            # Save retrain event to file
            self._save_event('retrain', retrain_entry)
    
    def get_current_metrics(self) -> Dict:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary with current metrics
        """
        if not self.metrics_history:
            return {}
        
        recent = self.metrics_history[-100:]  # Last 100 samples
        
        # Calculate metrics from recent history
        correct_predictions = sum(1 for m in recent if m.get('correct') is True)
        total_with_labels = sum(1 for m in recent if m.get('correct') is not None)
        
        recent_accuracy = correct_predictions / total_with_labels if total_with_labels > 0 else 0.0
        
        # Get latest recorded metrics
        latest = self.metrics_history[-1]
        
        return {
            'session_duration': str(datetime.now() - self.session_start),
            'total_predictions': self.total_predictions,
            'recent_accuracy': recent_accuracy,
            'recorded_accuracy': latest.get('accuracy', 0.0),
            'recorded_auc': latest.get('auc', 0.0),
            'drift_count': len(self.drift_events),
            'retrain_count': len(self.retrain_events),
            'last_drift': self.drift_events[-1] if self.drift_events else None,
            'last_retrain': self.retrain_events[-1] if self.retrain_events else None
        }
    
    def get_performance_trend(self, window: int = 100) -> Dict:
        """
        Get performance trend over recent window.
        
        Args:
            window: Number of recent samples to analyze
            
        Returns:
            Dictionary with trend statistics
        """
        if len(self.metrics_history) < 2:
            return {'trend': 'insufficient_data'}
        
        recent = self.metrics_history[-window:]
        
        # Extract accuracy values
        accuracies = [m['accuracy'] for m in recent if m.get('accuracy') is not None]
        
        if len(accuracies) < 2:
            return {'trend': 'insufficient_data'}
        
        # Calculate trend
        x = np.arange(len(accuracies))
        z = np.polyfit(x, accuracies, 1)
        slope = z[0]
        
        # Classify trend
        if slope > 0.001:
            trend = 'improving'
        elif slope < -0.001:
            trend = 'degrading'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'slope': float(slope),
            'current_accuracy': float(accuracies[-1]),
            'min_accuracy': float(np.min(accuracies)),
            'max_accuracy': float(np.max(accuracies)),
            'mean_accuracy': float(np.mean(accuracies)),
            'std_accuracy': float(np.std(accuracies))
        }
    
    def get_drift_statistics(self) -> Dict:
        """
        Get concept drift statistics.
        
        Returns:
            Dictionary with drift statistics
        """
        if not self.drift_events:
            return {
                'total_drifts': 0,
                'drifts_per_hour': 0.0,
                'avg_samples_between_drifts': 0
            }
        
        session_hours = (datetime.now() - self.session_start).total_seconds() / 3600
        drifts_per_hour = len(self.drift_events) / session_hours if session_hours > 0 else 0
        
        # Calculate samples between drifts
        drift_samples = [d['sample_number'] for d in self.drift_events]
        samples_between = []
        for i in range(1, len(drift_samples)):
            samples_between.append(drift_samples[i] - drift_samples[i-1])
        
        avg_between = np.mean(samples_between) if samples_between else 0
        
        return {
            'total_drifts': len(self.drift_events),
            'drifts_per_hour': float(drifts_per_hour),
            'avg_samples_between_drifts': float(avg_between),
            'recent_drifts': self.drift_events[-5:]  # Last 5 drifts
        }
    
    def print_dashboard(self) -> None:
        """Print ASCII dashboard to console."""
        print("\n" + "="*80)
        print("ONLINE LEARNING DASHBOARD".center(80))
        print("="*80 + "\n")
        
        # Current metrics
        metrics = self.get_current_metrics()
        print("📊 CURRENT PERFORMANCE")
        print("-" * 80)
        print(f"  Session Duration:     {metrics.get('session_duration', 'N/A')}")
        print(f"  Total Predictions:    {metrics.get('total_predictions', 0):,}")
        print(f"  Recent Accuracy:      {metrics.get('recent_accuracy', 0):.3f} (last 100 samples)")
        print(f"  Recorded Accuracy:    {metrics.get('recorded_accuracy', 0):.3f}")
        print(f"  Recorded AUC:         {metrics.get('recorded_auc', 0):.3f}")
        
        # Performance trend
        trend = self.get_performance_trend()
        print(f"\n📈 PERFORMANCE TREND")
        print("-" * 80)
        print(f"  Trend:                {trend.get('trend', 'N/A').upper()}")
        if trend.get('slope') is not None:
            print(f"  Slope:                {trend['slope']:+.6f}")
            print(f"  Mean Accuracy:        {trend.get('mean_accuracy', 0):.3f}")
            print(f"  Std Accuracy:         {trend.get('std_accuracy', 0):.3f}")
        
        # Drift statistics
        drift_stats = self.get_drift_statistics()
        print(f"\n🔔 CONCEPT DRIFT")
        print("-" * 80)
        print(f"  Total Drifts:         {drift_stats['total_drifts']}")
        print(f"  Drifts per Hour:      {drift_stats['drifts_per_hour']:.2f}")
        print(f"  Avg Samples Between:  {drift_stats.get('avg_samples_between_drifts', 0):.0f}")
        
        if drift_stats['total_drifts'] > 0:
            last_drift = metrics.get('last_drift')
            if last_drift:
                print(f"  Last Drift:           Sample {last_drift['sample_number']} "
                      f"(Accuracy: {last_drift.get('accuracy_at_drift', 0):.3f})")
        
        # Retraining events
        print(f"\n🔄 RETRAINING EVENTS")
        print("-" * 80)
        print(f"  Total Retrains:       {metrics.get('retrain_count', 0)}")
        if metrics.get('last_retrain'):
            last_retrain = metrics['last_retrain']
            print(f"  Last Retrain:         Sample {last_retrain['sample_number']} "
                  f"(Reason: {last_retrain['reason']})")
        
        print("\n" + "="*80 + "\n")
    
    def get_dashboard_json(self) -> str:
        """
        Get dashboard data as JSON.
        
        Returns:
            JSON string with all dashboard data
        """
        data = {
            'current_metrics': self.get_current_metrics(),
            'performance_trend': self.get_performance_trend(),
            'drift_statistics': self.get_drift_statistics(),
            'recent_history': self.metrics_history[-50:]  # Last 50 samples
        }
        
        return json.dumps(data, indent=2, default=str)
    
    def save_dashboard(self, filename: Optional[str] = None) -> str:
        """
        Save dashboard data to file.
        
        Args:
            filename: Custom filename (optional)
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_{timestamp}.json"
        
        filepath = self.log_dir / filename
        
        with open(filepath, 'w') as f:
            f.write(self.get_dashboard_json())
        
        return str(filepath)
    
    def _save_event(self, event_type: str, event_data: Dict) -> None:
        """
        Save event to log file.
        
        Args:
            event_type: Type of event ('drift' or 'retrain')
            event_data: Event data dictionary
        """
        event_file = self.log_dir / f"{event_type}_events.jsonl"
        
        with open(event_file, 'a') as f:
            f.write(json.dumps(event_data, default=str) + '\n')
    
    def generate_report(self) -> str:
        """
        Generate comprehensive text report.
        
        Returns:
            Report as string
        """
        lines = []
        lines.append("="*80)
        lines.append("ONLINE LEARNING PERFORMANCE REPORT".center(80))
        lines.append("="*80)
        lines.append("")
        
        # Session info
        lines.append(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Session Started:  {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Current metrics
        metrics = self.get_current_metrics()
        lines.append("PERFORMANCE SUMMARY")
        lines.append("-" * 80)
        lines.append(f"  Total Predictions:    {metrics.get('total_predictions', 0):,}")
        lines.append(f"  Recent Accuracy:      {metrics.get('recent_accuracy', 0):.3f}")
        lines.append(f"  Recorded Accuracy:    {metrics.get('recorded_accuracy', 0):.3f}")
        lines.append(f"  Recorded AUC:         {metrics.get('recorded_auc', 0):.3f}")
        lines.append("")
        
        # Trend analysis
        trend = self.get_performance_trend()
        lines.append("TREND ANALYSIS")
        lines.append("-" * 80)
        lines.append(f"  Trend Direction:      {trend.get('trend', 'N/A').upper()}")
        if trend.get('slope') is not None:
            lines.append(f"  Trend Slope:          {trend['slope']:+.6f}")
            lines.append(f"  Mean Accuracy:        {trend.get('mean_accuracy', 0):.3f}")
            lines.append(f"  Min Accuracy:         {trend.get('min_accuracy', 0):.3f}")
            lines.append(f"  Max Accuracy:         {trend.get('max_accuracy', 0):.3f}")
        lines.append("")
        
        # Drift analysis
        drift_stats = self.get_drift_statistics()
        lines.append("CONCEPT DRIFT ANALYSIS")
        lines.append("-" * 80)
        lines.append(f"  Total Drift Events:   {drift_stats['total_drifts']}")
        lines.append(f"  Drifts per Hour:      {drift_stats['drifts_per_hour']:.2f}")
        lines.append(f"  Avg Samples Between:  {drift_stats.get('avg_samples_between_drifts', 0):.0f}")
        lines.append("")
        
        # Recommendations
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 80)
        
        if trend.get('trend') == 'degrading':
            lines.append("  ⚠️  Performance is degrading. Consider:")
            lines.append("     - Reducing drift detection sensitivity")
            lines.append("     - Increasing retraining frequency")
            lines.append("     - Reviewing feature quality")
        elif trend.get('trend') == 'improving':
            lines.append("  ✅ Performance is improving. Current configuration working well.")
        else:
            lines.append("  ℹ️  Performance is stable.")
        
        if drift_stats['drifts_per_hour'] > 5:
            lines.append("  ⚠️  High drift frequency detected. Consider:")
            lines.append("     - Increasing drift detection threshold (delta parameter)")
            lines.append("     - Investigating root cause of frequent regime changes")
        
        lines.append("")
        lines.append("="*80)
        
        return "\n".join(lines)
    
    def export_metrics_csv(self, filename: Optional[str] = None) -> str:
        """
        Export metrics history to CSV.
        
        Args:
            filename: Custom filename (optional)
            
        Returns:
            Path to saved file
        """
        if not self.metrics_history:
            return ""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"metrics_{timestamp}.csv"
        
        filepath = self.log_dir / filename
        
        df = pd.DataFrame(self.metrics_history)
        df.to_csv(filepath, index=False)
        
        return str(filepath)


def create_dashboard_from_pipeline(pipeline) -> OnlineLearningDashboard:
    """
    Create dashboard and sync with existing pipeline state.
    
    Args:
        pipeline: OnlineLearningPipeline instance
        
    Returns:
        OnlineLearningDashboard instance
    """
    dashboard = OnlineLearningDashboard()
    
    # Sync state from pipeline
    status = pipeline.get_status()
    dashboard.total_predictions = status['performance']['n_samples']
    
    # Import history from pipeline
    if hasattr(pipeline.online_learner, 'performance_history'):
        for perf in pipeline.online_learner.performance_history:
            dashboard.metrics_history.append({
                'timestamp': perf['timestamp'],
                'accuracy': perf['accuracy'],
                'auc': perf['auc'],
                'n_samples': perf['n_samples']
            })
    
    return dashboard


if __name__ == "__main__":
    # Demo dashboard
    print("=== Online Learning Dashboard Demo ===\n")
    
    dashboard = OnlineLearningDashboard()
    
    # Simulate some predictions
    np.random.seed(42)
    
    print("Simulating 500 predictions with drift...\n")
    
    for i in range(500):
        # Simulate concept drift at sample 250
        if i < 250:
            accuracy = 0.70 + np.random.normal(0, 0.05)
        else:
            accuracy = 0.60 + np.random.normal(0, 0.05)  # Drift: accuracy drops
        
        drift_detected = (i == 250 or i == 251)  # Drift detection
        should_retrain = drift_detected
        
        dashboard.log_prediction(
            features={'x1': np.random.randn(), 'x2': np.random.randn()},
            prediction=np.random.randint(0, 2),
            true_label=np.random.randint(0, 2),
            confidence=np.random.uniform(0.5, 1.0),
            drift_detected=drift_detected,
            should_retrain=should_retrain,
            performance={'accuracy': accuracy, 'auc': accuracy - 0.05, 'n_samples': i + 1}
        )
    
    # Display dashboard
    dashboard.print_dashboard()
    
    # Generate report
    print("\n" + dashboard.generate_report())
    
    # Save dashboard
    saved_path = dashboard.save_dashboard()
    print(f"\n✅ Dashboard saved to: {saved_path}")
    
    # Export metrics
    csv_path = dashboard.export_metrics_csv()
    print(f"✅ Metrics exported to: {csv_path}")
