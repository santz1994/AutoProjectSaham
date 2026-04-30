"""
Enhanced Logging System for AutoSaham

Features:
1. Structured JSON logging
2. Correlation IDs for request tracking
3. Multiple log levels and handlers
4. Performance metrics
5. Log rotation
6. Contextual logging

Usage:
    from src.utils.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("Processing started", extra={'symbol': 'BBCA.JK'})
"""
import logging
import logging.handlers
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import contextvars


# Context variable for correlation ID
correlation_id_var = contextvars.ContextVar('correlation_id', default=None)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add correlation ID if available
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data['correlation_id'] = correlation_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add performance metrics if present
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        
        if hasattr(record, 'memory_mb'):
            log_data['memory_mb'] = record.memory_mb
        
        return json.dumps(log_data)


class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that adds contextual information."""
    
    def process(self, msg: str, kwargs: dict) -> tuple:
        """Add context to log records."""
        # Extract extra fields
        extra = kwargs.get('extra', {})
        
        # Add correlation ID
        correlation_id = correlation_id_var.get()
        if correlation_id:
            extra['correlation_id'] = correlation_id
        
        # Store extra fields in record
        if extra:
            if 'extra' not in kwargs:
                kwargs['extra'] = {}
            kwargs['extra']['extra_fields'] = extra
        
        return msg, kwargs


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    json_format: bool = False,
    rotation: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup enhanced logging system.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None = console only)
        json_format: Use JSON formatting
        rotation: Enable log rotation
        max_bytes: Max log file size before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("autosaham")
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    if json_format:
        console_formatter = JSONFormatter()
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        if rotation:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
        else:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        file_handler.setLevel(level)
        
        # Always use JSON format for file logs
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> ContextAdapter:
    """
    Get a logger with context support.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Context-aware logger adapter
    """
    logger = logging.getLogger(f"autosaham.{name}")
    return ContextAdapter(logger, {})


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """
    Set correlation ID for current context.
    
    Args:
        correlation_id: Correlation ID (generates new UUID if None)
        
    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Clear correlation ID from context."""
    correlation_id_var.set(None)


class LogContext:
    """Context manager for scoped logging with correlation ID."""
    
    def __init__(self, correlation_id: Optional[str] = None, **extra_fields):
        """
        Initialize log context.
        
        Args:
            correlation_id: Correlation ID (generates new if None)
            **extra_fields: Additional fields to include in logs
        """
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.extra_fields = extra_fields
        self.previous_correlation_id = None
    
    def __enter__(self):
        """Enter context."""
        self.previous_correlation_id = correlation_id_var.get()
        correlation_id_var.set(self.correlation_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context."""
        correlation_id_var.set(self.previous_correlation_id)
        return False


class PerformanceLogger:
    """Log performance metrics for operations."""
    
    def __init__(self, logger: logging.Logger, operation_name: str):
        """
        Initialize performance logger.
        
        Args:
            logger: Logger instance
            operation_name: Name of operation being measured
        """
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        """Start timing."""
        import time
        self.start_time = time.time()
        self.logger.debug(f"{self.operation_name} started")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End timing and log performance."""
        import time
        duration_ms = (time.time() - self.start_time) * 1000
        
        # Get memory usage (if psutil available)
        memory_mb = None
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except ImportError:
            pass
        
        extra = {
            'operation': self.operation_name,
            'duration_ms': round(duration_ms, 2)
        }
        
        if memory_mb:
            extra['memory_mb'] = round(memory_mb, 2)
        
        if exc_type is None:
            self.logger.info(
                f"{self.operation_name} completed in {duration_ms:.2f}ms",
                extra=extra
            )
        else:
            extra['error'] = str(exc_val)
            self.logger.error(
                f"{self.operation_name} failed after {duration_ms:.2f}ms",
                extra=extra
            )
        
        return False


# Default logger setup
setup_logging(
    level=logging.INFO,
    log_file='logs/autosaham.log',
    json_format=False,
    rotation=True
)


# Example usage
if __name__ == "__main__":
    # Setup logging
    setup_logging(level=logging.DEBUG, log_file='logs/test.log', json_format=False)
    
    # Get logger
    logger = get_logger(__name__)
    
    # Basic logging
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # Logging with extra fields
    logger.info("Processing symbol", extra={'symbol': 'BBCA.JK', 'price': 8450})
    
    # Using correlation ID
    with LogContext(extra_fields={'user_id': '12345'}):
        logger.info("Request started")
        logger.info("Processing...")
        logger.info("Request completed")
    
    # Performance logging
    with PerformanceLogger(logger.logger, "Data Fetching"):
        import time
        time.sleep(0.1)  # Simulate work
    
    print("\n✓ Check logs/test.log for output")

