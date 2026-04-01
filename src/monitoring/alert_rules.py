"""
Alert Rules Configuration
==========================

Defines alert thresholds and conditions for trading system monitoring.
Compatible with Prometheus AlertManager.

Timezone: Jakarta (WIB: UTC+7)
Currency: IDR
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

from src.data.idx_api_client import get_jakarta_now, JAKARTA_TZ


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    expr: str  # PromQL expression
    for_duration: str  # Duration before alert fires (e.g., "5m")
    severity: AlertSeverity
    annotations: Dict[str, str]  # Alert annotations (summary, runbook, etc.)


class TradingAlerts:
    """Trading system alert rules."""
    
    # ========================================================================
    # Order Execution Alerts
    # ========================================================================
    
    HIGH_ORDER_REJECTION_RATE = AlertRule(
        name="HighOrderRejectionRate",
        description="More than 10% of orders are being rejected",
        expr='(increase(trading_orders_rejected_total[5m]) / (increase(trading_orders_placed_total[5m]) + 1)) > 0.1',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "High order rejection rate detected",
            "description": "{{ $value | humanizePercentage }} of orders rejected in last 5 minutes",
            "impact": "Orders not executing properly",
            "action": "Check broker connection and order validation rules",
        }
    )
    
    ORDER_EXECUTION_TIMEOUT = AlertRule(
        name="OrderExecutionTimeout",
        description="Order execution taking too long (>5 seconds)",
        expr='histogram_quantile(0.95, rate(trading_order_execution_seconds_bucket[5m])) > 5',
        for_duration="3m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Slow order execution detected",
            "description": "95th percentile execution time: {{ $value }}s",
            "impact": "May miss trading opportunities",
            "action": "Check broker API latency and network connectivity",
        }
    )
    
    # ========================================================================
    # Broker Connection Alerts
    # ========================================================================
    
    BROKER_DISCONNECTED = AlertRule(
        name="BrokerDisconnected",
        description="Broker connection lost",
        expr='trading_broker_connection_status{broker=~".+"} == 0',
        for_duration="1m",
        severity=AlertSeverity.CRITICAL,
        annotations={
            "summary": "Broker {{ $labels.broker }} disconnected",
            "description": "Cannot execute trades",
            "impact": "Trading disabled",
            "action": "Reconnect broker immediately",
        }
    )
    
    HIGH_BROKER_ERROR_RATE = AlertRule(
        name="HighBrokerErrorRate",
        description="High error rate from broker API (>5 errors/min)",
        expr='rate(trading_broker_errors_total[1m]) > 0.0833',  # 5/min = 0.0833/sec
        for_duration="3m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "High API errors from {{ $labels.broker }}",
            "description": "Error rate: {{ $value | humanize }}/sec",
            "impact": "API may become unavailable",
            "action": "Check broker status and API quota usage",
        }
    )
    
    BROKER_LATENCY_HIGH = AlertRule(
        name="BrokerLatencyHigh",
        description="Broker API responses slow (p95 > 2 seconds)",
        expr='histogram_quantile(0.95, rate(trading_broker_request_latency_ms_bucket[5m])) > 2000',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Slow API responses from {{ $labels.broker }}",
            "description": "P95 latency: {{ $value }}ms",
            "impact": "Orders may not execute immediately",
            "action": "Check network connectivity and broker load",
        }
    )
    
    # ========================================================================
    # Position & Account Alerts
    # ========================================================================
    
    MARGIN_CALL_WARNING = AlertRule(
        name="MarginCallWarning",
        description="Account margin level below 150%",
        expr='trading_account_margin_level_percent < 150',
        for_duration="2m",
        severity=AlertSeverity.CRITICAL,
        annotations={
            "summary": "Margin call warning for {{ $labels.broker }}",
            "description": "Current margin: {{ $value }}%",
            "impact": "Risk of forced liquidation",
            "action": "Deposit funds or reduce positions immediately",
        }
    )
    
    LOW_BUYING_POWER = AlertRule(
        name="LowBuyingPower",
        description="Buying power below 10M IDR",
        expr='trading_account_buying_power_idr < 10000000',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Low buying power: {{ $value | humanize }} IDR",
            "description": "Cannot open new positions",
            "impact": "Trading opportunities may be missed",
            "action": "Monitor cash and adjust positions if needed",
        }
    )
    
    LARGE_UNREALIZED_LOSS = AlertRule(
        name="LargeUnrealizedLoss",
        description="Single position with >5% unrealized loss",
        expr='trading_position_unrealized_pl_percent < -5',
        for_duration="10m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Large loss in {{ $labels.symbol }}",
            "description": "Unrealized P&L: {{ $value }}%",
            "impact": "Position may trigger stop loss",
            "action": "Review position thesis and consider exit",
        }
    )
    
    # ========================================================================
    # Market Data Alerts
    # ========================================================================
    
    MARKET_DATA_STALENESS = AlertRule(
        name="MarketDataStale",
        description="Market data not updating (>30 seconds without update)",
        expr='time() - market_data_last_update_timestamp > 30',
        for_duration="1m",
        severity=AlertSeverity.CRITICAL,
        annotations={
            "summary": "Market data for {{ $labels.symbol }} is stale",
            "description": "Last update: {{ $value }}s ago",
            "impact": "Cannot make trading decisions",
            "action": "Check IDX API connection and data feed",
        }
    )
    
    HIGH_MARKET_DATA_LATENCY = AlertRule(
        name="HighMarketDataLatency",
        description="Market data latency > 100ms",
        expr='histogram_quantile(0.95, rate(trading_market_data_latency_ms_bucket[5m])) > 100',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Slow market data for {{ $labels.symbol }}",
            "description": "P95 latency: {{ $value }}ms",
            "impact": "Trading decisions may be delayed",
            "action": "Check network and IDX API status",
        }
    )
    
    # ========================================================================
    # Strategy Alerts
    # ========================================================================
    
    STRATEGY_LOSING_STREAK = AlertRule(
        name="StrategyLosingStreak",
        description="Strategy has 5+ consecutive losing trades",
        expr='rate(trading_strategy_losing_trades_total[1h]) / (rate(trading_strategy_losing_trades_total[1h]) + rate(trading_strategy_winning_trades_total[1h]) + 0.0001) > 0.8',
        for_duration="30m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Losing streak in {{ $labels.strategy }}",
            "description": "Win rate: {{ $value | humanizePercentage }}",
            "impact": "Strategy may be broken or market changed",
            "action": "Pause strategy and review recent signals",
        }
    )
    
    NEGATIVE_PNL = AlertRule(
        name="NegativePnL",
        description="Strategy cumulative PnL is negative",
        expr='trading_strategy_pnl_idr < 0',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "{{ $labels.strategy }} has negative PnL",
            "description": "Current PnL: {{ $value | humanize }} IDR",
            "impact": "Strategy is not profitable",
            "action": "Review strategy parameters and market conditions",
        }
    )
    
    HIGH_MAX_DRAWDOWN = AlertRule(
        name="HighMaxDrawdown",
        description="Maximum drawdown > 20%",
        expr='abs(trading_strategy_max_drawdown_percent) > 20',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "High drawdown in {{ $labels.strategy }}",
            "description": "Current drawdown: {{ $value }}%",
            "impact": "Strategy is risky",
            "action": "Reduce position size or pause strategy",
        }
    )
    
    # ========================================================================
    # Risk Alerts
    # ========================================================================
    
    HIGH_CONCENTRATION = AlertRule(
        name="HighConcentration",
        description="Portfolio concentration > 50% (top 3 symbols)",
        expr='trading_portfolio_concentration_percent > 50',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Portfolio concentration: {{ $value }}%",
            "description": "Top 3 symbols represent {{ $value }}% of portfolio",
            "impact": "Portfolio is not diversified",
            "action": "Rebalance to reduce concentration",
        }
    )
    
    HIGH_VALUE_AT_RISK = AlertRule(
        name="HighValueAtRisk",
        description="VaR (95%, 1-day) > 10% of equity",
        expr='trading_portfolio_var_idr > (trading_account_equity_idr * 0.1)',
        for_duration="5m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "High portfolio VaR",
            "description": "VaR: {{ $value | humanize }} IDR",
            "impact": "Potential large loss in adverse market conditions",
            "action": "Review risk limits and reduce position size",
        }
    )
    
    # ========================================================================
    # Anomaly Alerts
    # ========================================================================
    
    ANOMALY_DETECTED = AlertRule(
        name="AnomalyDetected",
        description="Anomaly detected in market data",
        expr='increase(trading_anomalies_detected_total[5m]) > 0',
        for_duration="1m",
        severity=AlertSeverity.INFO,
        annotations={
            "summary": "{{ $labels.anomaly_type }} anomaly in {{ $labels.symbol }}",
            "description": "Total anomalies this period: {{ $value | humanize }}",
            "impact": "Unusual market activity detected",
            "action": "Review recent price/volume action",
        }
    )
    
    PRICE_SPIKE_ANOMALY = AlertRule(
        name="PriceSpikeAnomaly",
        description="Price spike anomaly detected",
        expr='trading_anomaly_price_spike_detected{symbol=~".+"} == 1',
        for_duration="1m",
        severity=AlertSeverity.INFO,
        annotations={
            "summary": "Price spike in {{ $labels.symbol }}",
            "description": "Unusual price movement detected",
            "impact": "May indicate news or system issue",
            "action": "Check if spike is real or data error",
        }
    )
    
    VOLUME_SPIKE_ANOMALY = AlertRule(
        name="VolumeSpikeAnomaly",
        description="Volume spike anomaly detected",
        expr='trading_anomaly_volume_spike_detected{symbol=~".+"} == 1',
        for_duration="1m",
        severity=AlertSeverity.INFO,
        annotations={
            "summary": "Volume spike in {{ $labels.symbol }}",
            "description": "Unusual volume activity detected",
            "impact": "May indicate institutional activity or news",
            "action": "Monitor for continued volume",
        }
    )


class IdxComplianceAlerts:
    """IDX/BEI compliance monitoring alerts."""
    
    TRADING_HOURS_BEFORE_OPEN = AlertRule(
        name="OrderBeforeMarketOpen",
        description="Market not open yet (before 09:30 WIB)",
        expr='idx_session_status == 0',
        for_duration="1m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Trading order attempted outside market hours",
            "description": "Market status: {{ $value }}",
            "impact": "Order will be rejected",
            "action": "Only trade during 09:30-16:00 WIB",
        }
    )
    
    INVALID_SYMBOL_REJECTED = AlertRule(
        name="InvalidSymbolRejected",
        description="Order rejected due to invalid symbol",
        expr='increase(trading_orders_rejected_total{reason="invalid_symbol"}[5m]) > 0',
        for_duration="1m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Invalid symbol in order",
            "description": "Symbols must be *.JK format (e.g., BBCA.JK)",
            "impact": "Order not placed",
            "action": "Check symbol format",
        }
    )
    
    INVALID_LOT_SIZE_REJECTED = AlertRule(
        name="InvalidLotSizeRejected",
        description="Order rejected due to invalid lot size",
        expr='increase(trading_orders_rejected_total{reason="invalid_quantity"}[5m]) > 0',
        for_duration="1m",
        severity=AlertSeverity.WARNING,
        annotations={
            "summary": "Invalid lot size in order",
            "description": "Lot size must be multiple of 100 shares",
            "impact": "Order not placed",
            "action": "Use quantities in multiples of 100",
        }
    )


def get_all_alert_rules() -> List[AlertRule]:
    """Get all configured alert rules."""
    rules = []
    
    # Collect all AlertRule attributes from both classes
    for cls in [TradingAlerts, IdxComplianceAlerts]:
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if isinstance(attr, AlertRule):
                rules.append(attr)
    
    return rules


def generate_prometheus_alert_file(output_path: str) -> None:
    """Generate Prometheus alerting rules file (YAML)."""
    import yaml
    
    rules = get_all_alert_rules()
    
    # Convert AlertRule objects to dicts for YAML serialization
    rule_dicts = []
    for rule in rules:
        rule_dicts.append({
            "alert": rule.name,
            "expr": rule.expr,
            "for": rule.for_duration,
            "labels": {
                "severity": rule.severity.value,
                "component": "autosaham",
            },
            "annotations": {
                "summary": rule.annotations.get("summary", rule.description),
                "description": rule.annotations.get("description", ""),
                "impact": rule.annotations.get("impact", ""),
                "action": rule.annotations.get("action", ""),
            }
        })
    
    alert_config = {
        "groups": [
            {
                "name": "autosaham.rules",
                "interval": "30s",
                "rules": rule_dicts,
            }
        ]
    }
    
    with open(output_path, 'w') as f:
        yaml.dump(alert_config, f, default_flow_style=False)


if __name__ == "__main__":
    rules = get_all_alert_rules()
    print(f"Total alert rules configured: {len(rules)}")
    for rule in rules:
        print(f"  - {rule.name} ({rule.severity.value}): {rule.description}")
