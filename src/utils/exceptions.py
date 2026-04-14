"""
Custom Exception Classes for AutoSaham

Provides user-friendly error messages with:
1. Error categorization (User, System, External API)
2. Actionable suggestions
3. Documentation links
4. Error codes for tracking

Usage:
    from src.utils.exceptions import UserError, SystemError
    
    if invalid_input:
        raise UserError(
            "Invalid symbol format",
            suggestion="Use Forex/Crypto format (e.g., EURUSD=X or BTC-USD)",
            code="E1001"
        )
"""
from __future__ import annotations

from typing import Optional


class AutoSahamError(Exception):
    """Base exception for all AutoSaham errors."""
    
    def __init__(
        self,
        message: str,
        suggestion: Optional[str] = None,
        docs_link: Optional[str] = None,
        code: Optional[str] = None
    ):
        """
        Initialize AutoSaham error.
        
        Args:
            message: Error description
            suggestion: Suggested fix or action
            docs_link: Link to relevant documentation
            code: Error code for tracking
        """
        self.message = message
        self.suggestion = suggestion
        self.docs_link = docs_link
        self.code = code
        
        # Build full error message
        full_message = f"[{code}] {message}" if code else message
        
        if suggestion:
            full_message += f"\n💡 Suggestion: {suggestion}"
        
        if docs_link:
            full_message += f"\n📚 Documentation: {docs_link}"
        
        super().__init__(full_message)
    
    def to_dict(self) -> dict:
        """Convert error to dictionary (for API responses)."""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'suggestion': self.suggestion,
            'docs_link': self.docs_link,
            'code': self.code
        }


class UserError(AutoSahamError):
    """
    User input or configuration error.
    
    Examples:
    - Invalid symbol format
    - Missing API key
    - Invalid parameter values
    """
    pass


class SystemError(AutoSahamError):
    """
    Internal system error.
    
    Examples:
    - File I/O error
    - Database connection failed
    - Model loading failed
    """
    pass


class ExternalAPIError(AutoSahamError):
    """
    External API error (Yahoo Finance, NewsAPI, etc).
    
    Examples:
    - API rate limit exceeded
    - API authentication failed
    - Network timeout
    """
    pass


class DataValidationError(UserError):
    """Data validation failed."""
    pass


class ConfigurationError(UserError):
    """Configuration is invalid or missing."""
    pass


class ModelError(SystemError):
    """ML model related error."""
    pass


class DataFetchError(ExternalAPIError):
    """Failed to fetch data from external source."""
    pass


# Common error instances with suggestions
class CommonErrors:
    """Common pre-configured errors."""
    
    @staticmethod
    def missing_api_key(api_name: str) -> ConfigurationError:
        """API key missing error."""
        return ConfigurationError(
            f"{api_name} API key not configured",
            suggestion=f"Add {api_name}_KEY to your .env file",
            docs_link="https://github.com/your-repo/docs/setup.md",
            code="E1001"
        )
    
    @staticmethod
    def invalid_symbol(symbol: str) -> DataValidationError:
        """Invalid symbol format error."""
        return DataValidationError(
            f"Invalid symbol format: {symbol}",
            suggestion="Use Forex/Crypto format (e.g., EURUSD=X or BTC-USD)",
            code="E1002"
        )
    
    @staticmethod
    def model_not_found(model_path: str) -> ModelError:
        """Model file not found error."""
        return ModelError(
            f"Model file not found: {model_path}",
            suggestion="Train a model first: python scripts/train_model.py",
            code="E2001"
        )
    
    @staticmethod
    def data_not_found(symbol: str) -> DataFetchError:
        """Data not found error."""
        return DataFetchError(
            f"No data available for symbol: {symbol}",
            suggestion="Run ETL to fetch data: python -m src.main --run-etl --symbols {symbol}",
            code="E3001"
        )
    
    @staticmethod
    def api_rate_limit(api_name: str, retry_after: int) -> ExternalAPIError:
        """API rate limit error."""
        return ExternalAPIError(
            f"{api_name} rate limit exceeded",
            suggestion=f"Wait {retry_after} seconds before retrying",
            code="E3002"
        )
    
    @staticmethod
    def database_connection_failed(db_path: str) -> SystemError:
        """Database connection failed error."""
        return SystemError(
            f"Failed to connect to database: {db_path}",
            suggestion="Check if file exists and is not corrupted. Try deleting and recreating.",
            code="E2002"
        )
    
    @staticmethod
    def insufficient_data(symbol: str, required: int, available: int) -> DataValidationError:
        """Insufficient data error."""
        return DataValidationError(
            f"Insufficient data for {symbol}: need {required} bars, have {available}",
            suggestion=f"Fetch more historical data or reduce lookback period",
            code="E1003"
        )


def handle_exception(exc: Exception) -> dict:
    """
    Convert any exception to a standardized error response.
    
    Args:
        exc: Exception instance
        
    Returns:
        Dictionary with error details
    """
    if isinstance(exc, AutoSahamError):
        return exc.to_dict()
    
    # Handle standard Python exceptions
    error_type = exc.__class__.__name__
    
    # Map common exceptions to user-friendly messages
    suggestions = {
        'FileNotFoundError': 'Check if the file path is correct',
        'PermissionError': 'Check file/directory permissions',
        'ValueError': 'Check if the input value is valid',
        'KeyError': 'Check if the key exists in the data',
        'ImportError': 'Install missing package: pip install <package>',
        'ConnectionError': 'Check your internet connection',
    }
    
    return {
        'error_type': error_type,
        'message': str(exc),
        'suggestion': suggestions.get(error_type, 'Check the error message for details'),
        'docs_link': None,
        'code': None
    }


# Example usage
if __name__ == "__main__":
    # Example 1: User error
    try:
        symbol = "INVALID"
        if (not symbol.endswith('=X')) and ('-USD' not in symbol):
            raise CommonErrors.invalid_symbol(symbol)
    except AutoSahamError as e:
        print(f"Error caught: {e}\n")
        print(f"Error dict: {e.to_dict()}")
    
    # Example 2: System error
    try:
        model_path = "models/missing.joblib"
        raise CommonErrors.model_not_found(model_path)
    except AutoSahamError as e:
        print(f"\nError caught: {e}\n")
    
    # Example 3: External API error
    try:
        raise CommonErrors.api_rate_limit("NewsAPI", 60)
    except AutoSahamError as e:
        print(f"\nError caught: {e}\n")
