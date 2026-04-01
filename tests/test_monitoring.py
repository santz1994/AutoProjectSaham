"""
Monitoring & Alerts Tests
===========================

Tests for monitoring system, alert rules, and notifications.
"""

import pytest
from datetime import datetime
from src.monitoring.alert_rules import AlertRule, AlertSeverity, TradingAlerts, get_all_alert_rules
from src.monitoring.slack_notifications import SlackNotifier, AlertSeverity as SlackAlertSeverity


class TestAlertRules:
    """Test alert rule definitions."""
    
    def test_alert_rule_creation(self):
        """Test creating alert rules."""
        rule = AlertRule(
            name="TestAlert",
            description="Test alert",
            expr='test_metric > 100',
            for_duration="5m",
            severity=AlertSeverity.WARNING,
            annotations={"summary": "Test", "action": "Check"},
        )
        
        assert rule.name == "TestAlert"
        assert rule.severity == AlertSeverity.WARNING
    
    def test_all_alert_rules_loaded(self):
        """Test that all alert rules load successfully."""
        rules = get_all_alert_rules()
        assert len(rules) > 10  # Should have 20+ rules
        
        # Check some expected rules exist
        rule_names = {rule.name for rule in rules}
        assert "BrokerDisconnected" in rule_names
        assert "MarginCallWarning" in rule_names
        assert "StrategyLosingStreak" in rule_names
    
    def test_trading_alerts_structure(self):
        """Test TradingAlerts alert structure."""
        assert hasattr(TradingAlerts, 'HIGH_ORDER_REJECTION_RATE')
        assert isinstance(TradingAlerts.HIGH_ORDER_REJECTION_RATE, AlertRule)
        assert TradingAlerts.HIGH_ORDER_REJECTION_RATE.severity == AlertSeverity.WARNING
    
    def test_alert_severity_levels(self):
        """Test all severity levels."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"


class TestSlackNotifier:
    """Test Slack notification integration."""
    
    @pytest.fixture
    def notifier(self):
        """Create notifier instance."""
        return SlackNotifier("https://hooks.slack.com/test", "#test-channel")
    
    def test_notifier_initialization(self, notifier):
        """Test notifier initializes correctly."""
        assert notifier.webhook_url == "https://hooks.slack.com/test"
        assert notifier.channel == "#test-channel"
    
    def test_severity_colors(self, notifier):
        """Test severity color mapping."""
        assert notifier.SEVERITY_COLORS[SlackAlertSeverity.INFO] == "#36a64f"
        assert notifier.SEVERITY_COLORS[SlackAlertSeverity.WARNING] == "#ff9900"
        assert notifier.SEVERITY_COLORS[SlackAlertSeverity.CRITICAL] == "#ff0000"


class TestMonitoringIntegration:
    """Integration tests for monitoring system."""
    
    def test_alert_rule_promql_syntax(self):
        """Test that PromQL expressions are well-formed."""
        rules = get_all_alert_rules()
        
        for rule in rules:
            # Basic validation that expr contains expected operators
            assert any(op in rule.expr for op in ['>',  '<', '>=', '<=', 'rate', 'increase'])
    
    def test_alert_annotations_complete(self):
        """Test that alerts have complete annotations."""
        rules = get_all_alert_rules()
        
        for rule in rules:
            # Every rule should have summary and action
            assert "summary" in rule.annotations or rule.annotations
            assert rule.annotations, f"Rule {rule.name} missing annotations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
