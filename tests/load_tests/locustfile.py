"""
Locust Load Testing Suite
=========================

Load testing for AutoSaham Trading Platform
Tests all critical endpoints under concurrent load
Monitors performance metrics: response time, throughput, error rates

Jakarta timezone (WIB: UTC+7), IDX/IHSG, IDR, BEI compliance
"""

import random
from locust import HttpUser, task, between, events, TaskSet
from datetime import datetime, timedelta
import json

# Jakarta timezone aware timestamps
MARKET_OPEN = 10  # 09:30 WIB (adjusted to 10 for testing)
MARKET_CLOSE = 16  # 16:00 WIB
TRADING_SYMBOLS = ['BBCA.JK', 'BMRI.JK', 'TLKM.JK', 'ASII.JK', 'INDF.JK']


class TradingBehavior(TaskSet):
    """User behavior patterns for trading platform"""
    
    def on_start(self):
        """Initialize user session"""
        self.symbols = TRADING_SYMBOLS.copy()
        self.positions = {}
        self.pending_orders = []
    
    @task(3)
    def get_market_data(self):
        """GET /api/market/{symbol} - Most frequent"""
        symbol = random.choice(self.symbols)
        with self.client.get(
            f"/api/market/{symbol}",
            catch_response=True,
            name="/api/market/[symbol]"
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                # Verify IDX format and IDR currency
                assert symbol.endswith('.JK'), f"Invalid IDX symbol: {symbol}"
                assert data.get('currency') == 'IDR', "Currency must be IDR"
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(2)
    def get_account_info(self):
        """GET /api/account - Account info"""
        with self.client.get(
            "/api/account",
            catch_response=True,
            name="/api/account"
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                # Verify IDR currency
                assert data.get('currency') == 'IDR', "Account currency must be IDR"
                self.account_equity = data.get('total_equity_idr', 0)
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(2)
    def get_positions(self):
        """GET /api/positions - List positions"""
        with self.client.get(
            "/api/positions",
            catch_response=True,
            name="/api/positions"
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                self.positions = {p['symbol']: p for p in data.get('positions', [])}
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(1)
    def place_order(self):
        """POST /api/orders - Place order"""
        symbol = random.choice(self.symbols)
        quantity = random.choice([100, 200, 500])  # Minimum lot size: 100
        price = random.uniform(5000, 50000)  # IDR price range
        
        order_data = {
            'symbol': symbol,
            'side': random.choice(['BUY', 'SELL']),
            'quantity': quantity,
            'price': round(price, 0),
            'broker': random.choice(['stockbit', 'ajaib', 'indopremier']),
            'time_in_force': 'DAY'
        }
        
        with self.client.post(
            "/api/orders",
            json=order_data,
            catch_response=True,
            name="/api/orders"
        ) as response:
            if response.status_code in [200, 201]:
                response.success()
                data = response.json()
                order_id = data.get('order_id')
                if order_id:
                    self.pending_orders.append(order_id)
            elif response.status_code == 400:
                # Expected for validation errors
                response.success()
            else:
                response.failure(f"Expected 200/201, got {response.status_code}")
    
    @task(1)
    def get_orders(self):
        """GET /api/orders - List orders"""
        with self.client.get(
            "/api/orders",
            catch_response=True,
            name="/api/orders"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(1)
    def cancel_order(self):
        """DELETE /api/orders/{id} - Cancel order"""
        if self.pending_orders:
            order_id = self.pending_orders.pop(0)
            with self.client.delete(
                f"/api/orders/{order_id}",
                catch_response=True,
                name="/api/orders/[id]"
            ) as response:
                if response.status_code in [200, 404]:  # 404 if already cancelled
                    response.success()
                else:
                    response.failure(f"Expected 200/404, got {response.status_code}")
    
    @task(1)
    def get_strategy_performance(self):
        """GET /api/strategy/performance - Strategy metrics"""
        with self.client.get(
            "/api/strategy/performance",
            catch_response=True,
            name="/api/strategy/performance"
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                # Verify metrics in IDR
                assert 'total_pnl_idr' in data, "Missing total_pnl_idr"
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(1)
    def get_broker_status(self):
        """GET /api/brokers/status - Broker connectivity"""
        with self.client.get(
            "/api/brokers/status",
            catch_response=True,
            name="/api/brokers/status"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Expected 200, got {response.status_code}")
    
    @task(1)
    def get_alerts(self):
        """GET /api/alerts - Recent alerts"""
        with self.client.get(
            "/api/alerts?limit=10",
            catch_response=True,
            name="/api/alerts"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Expected 200, got {response.status_code}")


class TradingUser(HttpUser):
    """Simulated trading user"""
    
    tasks = [TradingBehavior]
    
    # Wait time between tasks: 1-5 seconds
    wait_time = between(1, 5)
    
    def on_start(self):
        """User starts session"""
        # Login if required
        login_response = self.client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "testpass"
            },
            catch_response=True
        )
        if login_response.status_code == 200:
            self.token = login_response.json().get('token')
            self.client.headers.update({
                'Authorization': f'Bearer {self.token}'
            })


class HighVolumeUser(HttpUser):
    """High-frequency trader"""
    
    tasks = [TradingBehavior]
    
    # High-frequency: 100-500ms between trades
    wait_time = between(0.1, 0.5)


class LowFrequencyUser(HttpUser):
    """Institutional/position trader"""
    
    tasks = [TradingBehavior]
    
    # Position trader: 10-30 seconds between actions
    wait_time = between(10, 30)


# Event handlers for metrics collection
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize test metrics"""
    print("\n" + "="*80)
    print("AUTOSAHAM LOAD TEST STARTED")
    print(f"Time: {datetime.now()} (Jakarta WIB)")
    print(f"Market: IDX/IHSG")
    print(f"Currency: IDR")
    print("Brokers: Stockbit, Ajaib, Indo Premier")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate final report"""
    print("\n" + "="*80)
    print("LOAD TEST COMPLETED")
    print("="*80)
    
    # Aggregate stats
    stats = environment.stats
    total_requests = sum(stats.total.num_requests for _ in [stats])
    total_failures = sum(stats.total.num_failures for _ in [stats])
    
    print(f"\nTotal Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {stats.total.fail_ratio:.2%}")
    print(f"Avg Response Time: {stats.total.avg_response_time:.0f}ms")
    print(f"P95 Response Time: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    print(f"P99 Response Time: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    print(f"Min Response Time: {stats.total.min_response_time:.0f}ms")
    print(f"Max Response Time: {stats.total.max_response_time:.0f}ms")
    print(f"RPS (Requests/sec): {stats.total.current_rps:.2f}")
    print("\n" + "="*80 + "\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, success, exception, **kwargs):
    """Log individual request metrics"""
    if not success:
        print(f"FAILED: {request_type} {name} - {response_time:.0f}ms")
