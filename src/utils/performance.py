"""
Performance Profiling & Optimization
======================================

Tools for profiling, monitoring, and optimizing performance
Includes database query optimization, cache management, and metrics collection

Jakarta timezone (WIB: UTC+7), IDX/IHSG, IDR, BEI compliance
"""

import time
import functools
from typing import Any, Callable, Dict, Optional
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for operations"""
    operation: str
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None
    memory_used_mb: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def cache_hit_ratio(self) -> float:
        """Calculate cache hit ratio"""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class PerformanceProfiler:
    """Profile and track performance metrics"""
    
    def __init__(self):
        self.metrics: Dict[str, list] = {}
        self.thresholds: Dict[str, float] = {
            'market_data': 100,      # 100ms for market data
            'orders': 500,           # 500ms for order operations
            'positions': 200,        # 200ms for position queries
            'broker_api': 1000,      # 1000ms for broker API calls
            'database': 100,         # 100ms for DB queries
        }
    
    def record_metric(self, metric: PerformanceMetrics):
        """Record a performance metric"""
        operation = metric.operation
        if operation not in self.metrics:
            self.metrics[operation] = []
        
        self.metrics[operation].append(metric)
        
        # Log if exceeds threshold
        threshold = self.thresholds.get(operation, 1000)
        if metric.duration_ms > threshold:
            logger.warning(
                f"Performance threshold exceeded: {operation} "
                f"({metric.duration_ms:.0f}ms > {threshold}ms)"
            )
    
    def get_stats(self, operation: str) -> Dict[str, Any]:
        """Get statistics for an operation"""
        if operation not in self.metrics or not self.metrics[operation]:
            return {}
        
        durations = [m.duration_ms for m in self.metrics[operation]]
        
        return {
            'operation': operation,
            'count': len(durations),
            'min_ms': min(durations),
            'max_ms': max(durations),
            'avg_ms': sum(durations) / len(durations),
            'p95_ms': sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
            'p99_ms': sorted(durations)[int(len(durations) * 0.99)] if durations else 0,
            'threshold_ms': self.thresholds.get(operation, 1000),
        }
    
    def print_report(self):
        """Print performance report"""
        print("\n" + "="*100)
        print("PERFORMANCE PROFILING REPORT")
        print(f"Timestamp: {datetime.now()} (Jakarta WIB)")
        print("="*100)
        
        for operation in sorted(self.metrics.keys()):
            stats = self.get_stats(operation)
            if stats:
                print(f"\n{operation.upper()}")
                print(f"  Count: {stats['count']}")
                print(f"  Min: {stats['min_ms']:.0f}ms")
                print(f"  Max: {stats['max_ms']:.0f}ms")
                print(f"  Avg: {stats['avg_ms']:.0f}ms")
                print(f"  P95: {stats['p95_ms']:.0f}ms (Threshold: {stats['threshold_ms']}ms)")
                print(f"  P99: {stats['p99_ms']:.0f}ms")
        
        print("\n" + "="*100 + "\n")


# Global profiler instance
_profiler = PerformanceProfiler()


@contextmanager
def profile_operation(operation: str, category: Optional[str] = None):
    """Context manager for profiling operations"""
    start_time = time.time()
    metric = PerformanceMetrics(operation=operation)
    
    try:
        yield metric
        metric.success = True
    except Exception as e:
        metric.error = str(e)
        metric.success = False
        raise
    finally:
        metric.duration_ms = (time.time() - start_time) * 1000
        _profiler.record_metric(metric)


def profile_function(category: str = 'default'):
    """Decorator for profiling function execution"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            operation_name = f"{category}:{func.__name__}"
            with profile_operation(operation_name):
                return func(*args, **kwargs)
        return wrapper
    return decorator


class CacheConfig:
    """Cache configuration for AutoSaham"""
    
    def __init__(self):
        # Default TTL values (in seconds)
        self.ttl_config = {
            'market_data': 5,          # Market data: 5 seconds
            'account_info': 30,        # Account info: 30 seconds
            'positions': 10,           # Positions: 10 seconds
            'broker_status': 20,       # Broker status: 20 seconds
            'symbol_metadata': 3600,   # Symbol metadata: 1 hour
            'features': 30,            # ML features: 30 seconds
        }
        
        # Cache size limits (in MB)
        self.size_limits = {
            'market_data': 100,
            'account_info': 10,
            'positions': 50,
            'features': 500,
        }
        
        # Enable/disable caching
        self.enabled = True
        self.max_memory_mb = 1000
    
    def get_ttl(self, cache_type: str) -> int:
        """Get TTL for cache type"""
        return self.ttl_config.get(cache_type, 300)
    
    def get_size_limit(self, cache_type: str) -> int:
        """Get size limit for cache type (in MB)"""
        return self.size_limits.get(cache_type, 100)


class QueryOptimizer:
    """Database query optimization hints"""
    
    # Query optimization patterns
    OPTIMIZATION_PATTERNS = {
        'market_data': {
            'indexes': ['symbol', 'timestamp'],
            'batch_size': 1000,
            'cache_ttl': 5,
            'description': 'Query latest price/OHLCV data'
        },
        'positions': {
            'indexes': ['account_id', 'symbol'],
            'batch_size': 250,
            'cache_ttl': 10,
            'description': 'Query account positions'
        },
        'orders': {
            'indexes': ['account_id', 'created_at'],
            'batch_size': 500,
            'cache_ttl': 0,  # No cache for orders
            'description': 'Query order history'
        },
        'trades': {
            'indexes': ['account_id', 'execution_time'],
            'batch_size': 1000,
            'cache_ttl': 30,
            'description': 'Query trade history'
        },
    }
    
    @classmethod
    def get_optimization_hint(cls, query_type: str) -> Dict[str, Any]:
        """Get optimization hint for query type"""
        return cls.OPTIMIZATION_PATTERNS.get(query_type, {})


class BenchmarkResult:
    """Benchmark result"""
    
    def __init__(self, name: str, iterations: int = 1000):
        self.name = name
        self.iterations = iterations
        self.times = []
    
    def add_time(self, duration_ms: float):
        """Add measured time"""
        self.times.append(duration_ms)
    
    def get_stats(self) -> Dict[str, float]:
        """Get benchmark statistics"""
        if not self.times:
            return {}
        
        sorted_times = sorted(self.times)
        total = sum(self.times)
        
        return {
            'name': self.name,
            'iterations': len(self.times),
            'total_ms': total,
            'avg_ms': total / len(self.times),
            'min_ms': min(self.times),
            'max_ms': max(self.times),
            'p95_ms': sorted_times[int(len(sorted_times) * 0.95)],
            'p99_ms': sorted_times[int(len(sorted_times) * 0.99)],
            'ops_per_sec': len(self.times) / (total / 1000),
        }


def benchmark_operation(func: Callable, iterations: int = 1000) -> BenchmarkResult:
    """Benchmark a function"""
    result = BenchmarkResult(func.__name__, iterations)
    
    for _ in range(iterations):
        start = time.time()
        try:
            func()
        except:
            pass  # Ignore errors in benchmark
        finally:
            elapsed_ms = (time.time() - start) * 1000
            result.add_time(elapsed_ms)
    
    return result


# Performance monitoring integration
class PerformanceMonitor:
    """Monitor performance in production"""
    
    def __init__(self):
        self.profiler = PerformanceProfiler()
        self.cache_config = CacheConfig()
        self.slow_queries = []
        self.slow_operations = []
    
    def log_slow_operation(self, operation: str, duration_ms: float, threshold_ms: float):
        """Log slow operation"""
        if duration_ms > threshold_ms:
            self.slow_operations.append({
                'operation': operation,
                'duration_ms': duration_ms,
                'threshold_ms': threshold_ms,
                'timestamp': datetime.now()
            })
            logger.warning(
                f"Slow operation detected: {operation} "
                f"({duration_ms:.0f}ms > {threshold_ms:.0f}ms)"
            )
    
    def report_slow_operations(self, top_n: int = 10):
        """Report top slow operations"""
        sorted_ops = sorted(
            self.slow_operations,
            key=lambda x: x['duration_ms'],
            reverse=True
        )[:top_n]
        
        print("\nTop Slow Operations:")
        for op in sorted_ops:
            print(f"  {op['operation']}: {op['duration_ms']:.0f}ms")


# Global monitor instance
performance_monitor = PerformanceMonitor()
