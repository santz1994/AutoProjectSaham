"""
Grafana Dashboard Definitions
==============================

Generates production-grade Grafana dashboard JSON for system monitoring.
Compatible with Grafana 8.0+

Timezone: Jakarta (WIB: UTC+7)
"""

import json
from typing import Dict, List, Any


def create_trading_dashboard() -> Dict[str, Any]:
    """Create main trading dashboard."""
    return {
        "dashboard": {
            "title": "AutoSaham Trading Dashboard",
            "description": "Real-time trading system monitoring",
            "tags": ["autosaham", "trading", "production"],
            "timezone": "Asia/Jakarta",
            "panels": [
                # Row: Orders
                {
                    "id": 1,
                    "title": "Orders",
                    "type": "row",
                    "collapsed": False,
                },
                # Orders placed (today)
                {
                    "id": 2,
                    "title": "Orders Placed (Today)",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'increase(trading_orders_placed_total[1d])',
                            "legendFormat": "{{ symbol }} - {{ side }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 1},
                },
                # Order success rate
                {
                    "id": 3,
                    "title": "Order Success Rate",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": '100 * (increase(trading_orders_filled_total[1h]) / (increase(trading_orders_placed_total[1h]) + 0.001))',
                            "legendFormat": "Success Rate",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 6, "x": 12, "y": 1},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "max": 100,
                        }
                    }
                },
                # Avg execution time
                {
                    "id": 4,
                    "title": "Avg Order Execution Time",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": '1000 * histogram_quantile(0.95, rate(trading_order_execution_seconds_bucket[5m]))',
                            "legendFormat": "P95 (ms)",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 6, "x": 18, "y": 1},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "ms",
                        }
                    }
                },
                
                # Row: Positions
                {
                    "id": 5,
                    "title": "Positions",
                    "type": "row",
                    "collapsed": False,
                    "gridPos": {"h": 1, "w": 24, "x": 0, "y": 9},
                },
                # Portfolio value
                {
                    "id": 6,
                    "title": "Portfolio Market Value",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'sum(trading_position_value_idr) by (broker)',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 10},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                            "custom": {
                                "hideFrom": {
                                    "tooltip": False,
                                    "viz": False,
                                    "legend": False
                                }
                            }
                        }
                    }
                },
                # Position P&L
                {
                    "id": 7,
                    "title": "Unrealized P&L by Symbol",
                    "type": "table",
                    "targets": [
                        {
                            "expr": 'trading_position_unrealized_pl_idr',
                            "format": "table",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 10},
                },
                
                # Row: Account
                {
                    "id": 8,
                    "title": "Account Status",
                    "type": "row",
                    "collapsed": False,
                    "gridPos": {"h": 1, "w": 24, "x": 0, "y": 18},
                },
                # Cash balance
                {
                    "id": 9,
                    "title": "Cash Balance",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_account_cash_idr',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 6, "w": 6, "x": 0, "y": 19},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                            "color": {
                                "mode": "thresholds",
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": None},
                                        {"color": "yellow", "value": 10000000},
                                        {"color": "green", "value": 50000000},
                                    ]
                                }
                            }
                        }
                    }
                },
                # Total equity
                {
                    "id": 10,
                    "title": "Total Equity",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_account_equity_idr',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 6, "w": 6, "x": 6, "y": 19},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                        }
                    }
                },
                # Buying power
                {
                    "id": 11,
                    "title": "Buying Power",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_account_buying_power_idr',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 6, "w": 6, "x": 12, "y": 19},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                        }
                    }
                },
                # Margin level
                {
                    "id": 12,
                    "title": "Margin Level",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_account_margin_level_percent',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 6, "w": 6, "x": 18, "y": 19},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "color": {
                                "mode": "thresholds",
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": None},
                                        {"color": "yellow", "value": 150},
                                        {"color": "green", "value": 200},
                                    ]
                                }
                            }
                        }
                    }
                },
            ],
            "refresh": "10s",
            "time": {
                "from": "now-24h",
                "to": "now",
            },
        }
    }


def create_broker_dashboard() -> Dict[str, Any]:
    """Create broker connectivity & performance dashboard."""
    return {
        "dashboard": {
            "title": "Broker Performance",
            "description": "Broker API performance and connectivity monitoring",
            "tags": ["autosaham", "brokers", "connectivity"],
            "timezone": "Asia/Jakarta",
            "panels": [
                # Broker status
                {
                    "id": 1,
                    "title": "Broker Connection Status",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_broker_connection_status',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 6, "w": 24, "x": 0, "y": 0},
                    "fieldConfig": {
                        "defaults": {
                            "color": {
                                "mode": "thresholds",
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": None},
                                        {"color": "green", "value": 1},
                                    ]
                                }
                            },
                            "custom": {
                                "hideFrom": {
                                    "tooltip": False,
                                    "viz": False,
                                    "legend": False
                                }
                            }
                        }
                    }
                },
                # Latency by broker
                {
                    "id": 2,
                    "title": "API Latency by Broker",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'histogram_quantile(0.95, rate(trading_broker_request_latency_ms_bucket[5m]))',
                            "legendFormat": "{{ broker }} P95",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "ms",
                        }
                    }
                },
                # Error rate
                {
                    "id": 3,
                    "title": "Error Rate by Broker",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'rate(trading_broker_errors_total[1m])',
                            "legendFormat": "{{ broker }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                        }
                    }
                },
                # Request distribution
                {
                    "id": 4,
                    "title": "Requests by Endpoint",
                    "type": "piechart",
                    "targets": [
                        {
                            "expr": 'sum(rate(trading_broker_request_latency_ms_count[5m])) by (endpoint)',
                            "legendFormat": "{{ endpoint }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 14},
                },
                # Error types
                {
                    "id": 5,
                    "title": "Error Types Distribution",
                    "type": "piechart",
                    "targets": [
                        {
                            "expr": 'sum(increase(trading_broker_errors_total[1h])) by (error_type)',
                            "legendFormat": "{{ error_type }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 14},
                },
            ],
            "refresh": "30s",
            "time": {
                "from": "now-1h",
                "to": "now",
            },
        }
    }


def create_strategy_dashboard() -> Dict[str, Any]:
    """Create strategy performance dashboard."""
    return {
        "dashboard": {
            "title": "Strategy Performance",
            "description": "Trading strategy metrics and P&L tracking",
            "tags": ["autosaham", "strategy", "performance"],
            "timezone": "Asia/Jakarta",
            "panels": [
                # Total P&L
                {
                    "id": 1,
                    "title": "Cumulative P&L",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'trading_strategy_pnl_idr',
                            "legendFormat": "{{ strategy }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                            "color": {
                                "mode": "thresholds",
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": None},
                                        {"color": "yellow", "value": 0},
                                        {"color": "green", "value": 1000000},
                                    ]
                                }
                            }
                        }
                    }
                },
                # Win rate
                {
                    "id": 2,
                    "title": "Win Rate",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": '100 * (trading_strategy_winning_trades_total / (trading_strategy_winning_trades_total + trading_strategy_losing_trades_total))',
                            "legendFormat": "{{ strategy }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                        }
                    }
                },
                # Sharpe ratio
                {
                    "id": 3,
                    "title": "Sharpe Ratio",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": 'trading_strategy_sharpe_ratio',
                            "legendFormat": "{{ strategy }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "short",
                        }
                    }
                },
                # Drawdown
                {
                    "id": 4,
                    "title": "Maximum Drawdown",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'trading_strategy_max_drawdown_percent',
                            "legendFormat": "{{ strategy }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "color": {
                                "mode": "palette-classic",
                            }
                        }
                    }
                },
                # Signals
                {
                    "id": 5,
                    "title": "Signals Generated",
                    "type": "graph",
                    "targets": [
                        {
                            "expr": 'increase(trading_strategy_signal_generated_total[1d])',
                            "legendFormat": "{{ strategy }} - {{ signal_type }}",
                        }
                    ],
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                },
                # Trade history
                {
                    "id": 6,
                    "title": "Recent Trades",
                    "type": "table",
                    "targets": [
                        {
                            "expr": 'topk(20, trading_strategy_winning_trades_total)',
                        }
                    ],
                    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16},
                },
            ],
            "refresh": "30s",
            "time": {
                "from": "now-7d",
                "to": "now",
            },
        }
    }


def save_dashboards_to_files(output_dir: str = "monitoring/grafana") -> None:
    """Save all dashboards to JSON files."""
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    dashboards = [
        ("trading", create_trading_dashboard()),
        ("brokers", create_broker_dashboard()),
        ("strategy", create_strategy_dashboard()),
    ]
    
    for name, dashboard in dashboards:
        filepath = os.path.join(output_dir, f"{name}-dashboard.json")
        with open(filepath, 'w') as f:
            json.dump(dashboard, f, indent=2)
        print(f"Created: {filepath}")


if __name__ == "__main__":
    import os
    
    # Create output directory
    output_dir = "monitoring/grafana"
    os.makedirs(output_dir, exist_ok=True)
    
    save_dashboards_to_files(output_dir)
