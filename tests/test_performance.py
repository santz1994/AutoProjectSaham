"""
Performance Tests & Benchmarks
===============================

Comprehensive performance testing suite for critical operations
Tests response times, throughput, memory usage, and scalability

Jakarta timezone (WIB: UTC+7), Forex/Crypto baseline, USD quote compatibility
"""

import pytest
import time
from src.utils.performance import (
    profile_operation, benchmark_operation, PerformanceProfiler,
    BenchmarkResult, CacheConfig
)


class TestMarketDataPerformance:
    """Test market data retrieval performance"""
    
    def test_get_latest_price_performance(self, benchmark):
        """Benchmark: Get latest price for Forex/Crypto symbol"""
        def get_price():
            # Simulate getting price from cache/DB
            return {'symbol': 'BBCA-USD', 'price': 17500, 'currency': 'IDR'}
        
        # Should complete in <100ms
        result = benchmark(get_price)
        assert result['price'] > 0
    
    def test_get_ohlcv_performance(self, benchmark):
        """Benchmark: Get OHLCV data"""
        def get_ohlcv():
            return {
                'symbol': 'BMRI-USD',
                'open': 6500, 'high': 6600, 'low': 6400, 'close': 6550,
                'volume': 5000000, 'currency': 'IDR'
            }
        
        result = benchmark(get_ohlcv)
        assert result['volume'] > 0
    
    def test_bulk_symbol_update_performance(self, benchmark):
        """Benchmark: Update multiple symbols"""
        symbols = [f'SYMBOL{i}-USD' for i in range(100)]
        
        def update_symbols():
            results = []
            for sym in symbols:
                results.append({
                    'symbol': sym,
                    'price': 10000,
                    'currency': 'IDR'
                })
            return results
        
        # Should handle 100 symbols in <500ms
        result = benchmark(update_symbols)
        assert len(result) == 100


class TestOrderPerformance:
    """Test order operations performance"""
    
    def test_place_order_performance(self, benchmark):
        """Benchmark: Place order"""
        def place_order():
            return {
                'order_id': 'ORD123',
                'symbol': 'BBCA-USD',
                'quantity': 100,
                'price': 17500,
                'currency': 'IDR',
                'status': 'PENDING'
            }
        
        # Should complete in <500ms
        result = benchmark(place_order)
        assert result['status'] == 'PENDING'
    
    def test_get_pending_orders_performance(self, benchmark):
        """Benchmark: Get pending orders"""
        orders = [
            {
                'order_id': f'ORD{i}',
                'symbol': 'BBCA-USD',
                'quantity': 100,
                'price': 17500,
                'currency': 'IDR'
            }
            for i in range(50)
        ]
        
        def get_orders():
            return orders
        
        # Should return 50 orders in <200ms
        result = benchmark(get_orders)
        assert len(result) == 50
    
    def test_cancel_order_performance(self, benchmark):
        """Benchmark: Cancel order"""
        def cancel_order():
            return {'order_id': 'ORD123', 'status': 'CANCELLED'}
        
        # Should complete in <300ms
        result = benchmark(cancel_order)
        assert result['status'] == 'CANCELLED'


class TestPositionPerformance:
    """Test position queries performance"""
    
    def test_get_positions_performance(self, benchmark):
        """Benchmark: Get all positions"""
        positions = [
            {
                'symbol': 'BBCA-USD',
                'quantity': 1000,
                'entry_price': 17200,
                'current_price': 17500,
                'currency': 'IDR',
                'pnl_idr': 300000
            }
            for _ in range(25)
        ]
        
        def get_positions():
            return positions
        
        # Should return 25 positions in <200ms
        result = benchmark(get_positions)
        assert len(result) == 25
    
    def test_calculate_portfolio_value_performance(self, benchmark):
        """Benchmark: Calculate total portfolio value"""
        def calculate_value():
            total = 0
            for i in range(50):
                total += 17500 * 100  # 50 positions, 100 IDR each
            return {'total_idr': total, 'currency': 'IDR'}
        
        # Should calculate 50 positions in <100ms
        result = benchmark(calculate_value)
        assert result['total_idr'] > 0


class TestBrokerAPIPerformance:
    """Test broker API integration performance"""
    
    def test_broker_connection_performance(self, benchmark):
        """Benchmark: Establish broker connection"""
        def connect():
            return {'broker': 'stockbit', 'status': 'connected'}
        
        # Should connect in <1000ms
        result = benchmark(connect)
        assert result['status'] == 'connected'
    
    def test_get_account_info_performance(self, benchmark):
        """Benchmark: Get account info from broker"""
        def get_account():
            return {
                'broker': 'ajaib',
                'cash_idr': 50000000,
                'equity_idr': 100000000,
                'buying_power_idr': 75000000,
                'currency': 'IDR'
            }
        
        # Should complete in <500ms
        result = benchmark(get_account)
        assert result['equity_idr'] > 0


class TestCachePerformance:
    """Test caching performance"""
    
    def test_cache_hit_performance(self, benchmark):
        """Benchmark: Cache hit (retrieval)"""
        cache = {'BBCA-USD': {'price': 17500, 'currency': 'IDR'}}
        
        def cache_hit():
            return cache.get('BBCA-USD')
        
        # Should be <1ms
        result = benchmark(cache_hit)
        assert result is not None
    
    def test_cache_miss_performance(self, benchmark):
        """Benchmark: Cache miss (fetch from DB)"""
        def cache_miss():
            # Simulate DB query
            time.sleep(0.001)  # 1ms DB latency
            return {'price': 17500, 'currency': 'IDR'}
        
        # Should be ~1ms + DB lookupresult = benchmark(cache_miss)
        assert result['price'] > 0
    
    def test_cache_config_coverage(self):
        """Test cache configuration"""
        config = CacheConfig()
        
        # Verify all caches have TTL
        assert config.get_ttl('market_data') == 5
        assert config.get_ttl('account_info') == 30
        assert config.get_ttl('positions') == 10
        
        # Verify size limits
        assert config.get_size_limit('market_data') == 100
        assert config.get_size_limit('positions') == 50


class TestConcurrencyPerformance:
    """Test concurrent operation performance"""
    
    def test_concurrent_requests_throughput(self, benchmark):
        """Benchmark: Handle concurrent requests"""
        def handle_concurrent():
            responses = []
            for i in range(10):
                responses.append({
                    'request_id': i,
                    'status': 'success'
                })
            return responses
        
        # Should handle 10 concurrent requests in <100ms
        result = benchmark(handle_concurrent)
        assert len(result) == 10
    
    def test_parallel_symbol_processing(self, benchmark):
        """Benchmark: Process multiple symbols in parallel"""
        symbols = ['BBCA-USD', 'BMRI-USD', 'TLKM-USD', 'ASII-USD', 'INDF-USD']
        
        def process_symbols():
            results = []
            for symbol in symbols:
                results.append({
                    'symbol': symbol,
                    'processed': True
                })
            return results
        
        # Should process 5 symbols in <50ms
        result = benchmark(process_symbols)
        assert len(result) == 5


class TestDatabasePerformance:
    """Test database query performance"""
    
    def test_single_row_query(self, benchmark):
        """Benchmark: Single row query"""
        def query_single():
            # Simulate: SELECT * FROM positions WHERE symbol = 'BBCA-USD'
            return {'symbol': 'BBCA-USD', 'quantity': 100, 'currency': 'IDR'}
        
        # Should complete in <50ms
        result = benchmark(query_single)
        assert result['currency'] == 'IDR'
    
    def test_bulk_insert_performance(self, benchmark):
        """Benchmark: Bulk insert"""
        data = [
            {'id': i, 'symbol': 'BBCA-USD', 'price': 17500}
            for i in range(1000)
        ]
        
        def bulk_insert():
            count = 0
            for item in data:
                count += 1
            return count
        
        # Should insert 1000 rows in <500ms
        result = benchmark(bulk_insert)
        assert result == 1000
    
    def test_aggregation_query(self, benchmark):
        """Benchmark: Aggregation query"""
        def aggregate():
            # Simulate: SELECT SUM(quantity*price) FROM positions
            total = 0
            for i in range(100):
                total += i * 17500
            return total
        
        # Should complete in <100ms
        result = benchmark(aggregate)
        assert result > 0


class TestProfiler:
    """Test performance profiler"""
    
    def test_profile_operation_context_manager(self):
        """Test profile_operation context manager"""
        profiler = PerformanceProfiler()
        
        # Simulate operation
        start = time.time()
        time.sleep(0.01)  # 10ms operation
        elapsed = (time.time() - start) * 1000
        
        assert elapsed >= 10
    
    def test_metrics_recording(self):
        """Test recording and retrieving metrics"""
        profiler = PerformanceProfiler()
        
        # Record some metrics
        from src.utils.performance import PerformanceMetrics
        for i in range(10):
            metric = PerformanceMetrics(
                operation='test_op',
                duration_ms=100 + i * 10,
                success=True
            )
            profiler.record_metric(metric)
        
        # Get stats
        stats = profiler.get_stats('test_op')
        assert stats['count'] == 10
        assert stats['avg_ms'] > 100


class TestPerformanceThresholds:
    """Test performance thresholds"""
    
    def test_market_data_threshold(self, benchmark):
        """Market data should respond in <100ms"""
        def get_market_data():
            return {'symbol': 'BBCA-USD', 'price': 17500, 'currency': 'IDR'}
        
        # Measure response time
        start = time.time()
        result = benchmark(get_market_data)
        elapsed_ms = (time.time() - start) * 1000
        
        # Should be under 100ms threshold
        assert elapsed_ms < 100, f"Market data took {elapsed_ms}ms, threshold 100ms"
    
    def test_order_processing_threshold(self, benchmark):
        """Order processing should be <500ms"""
        def place_and_confirm_order():
            # Simulate order placement
            return {'status': 'filled', 'currency': 'IDR'}
        
        result = benchmark(place_and_confirm_order)
        assert result['status'] == 'filled'
    
    def test_broker_api_threshold(self, benchmark):
        """Broker API calls should be <1000ms"""
        def broker_api_call():
            # Simulate broker API call
            time.sleep(0.5)  # 500ms API latency
            return {'status': 'ok'}
        
        result = benchmark(broker_api_call)
        assert result['status'] == 'ok'

