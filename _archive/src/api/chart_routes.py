"""
Chart API Endpoints
====================

FastAPI routes for chart data service with real-time WebSocket support.

Endpoints:
- GET /api/charts/metadata/{symbol}  - Get chart metadata
- GET /api/charts/candles/{symbol}   - Get OHLCV candles
- WS /ws/charts/{symbol}            - WebSocket for real-time updates

Author: AutoSaham Team
Version: 1.0.0
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import JSONResponse

from src.api.chart_service import (
    TimeFrame,
    MarketSymbolValidator,
    get_chart_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/charts", tags=["charts"])
ws_router = APIRouter(prefix="/ws", tags=["websocket"])


@router.get("/metadata/{symbol}")
async def get_chart_metadata(symbol: str):
    """
    Get chart metadata for Forex/Crypto symbol.
    
    Args:
        symbol: Forex/Crypto symbol (e.g., "EURUSD=X", "BTC-USD")
        
    Returns:
        Chart metadata including trading hours, currency,decimals
        
    Example:
        GET /api/charts/metadata/EURUSD=X
        
        Response:
        {
            "symbol": "EURUSD=X",
            "exchange": "FOREX",
            "currency": "USD",
            "timeFrame": "1d",
            "decimalPlaces": 5,
            "minLotSize": 0.01,
            "tradingStart": "00:00",
            "tradingEnd": "23:59",
            "timezone": "Asia/Jakarta"
        }
    """
    try:
        # Validate symbol
        is_valid, error = MarketSymbolValidator.validate(symbol)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)
        
        # Get metadata
        metadata = MarketSymbolValidator.get_metadata(symbol)
        
        return JSONResponse(metadata.to_dict())
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting metadata for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles/{symbol}")
async def get_chart_candles(
    symbol: str,
    timeframe: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo"),
    limit: int = Query(100, ge=1, le=1000, description="Number of candles (1-1000)"),
):
    """
    Get OHLCV candles for Forex/Crypto symbol.
    
    Args:
        symbol: Forex/Crypto symbol (e.g., "EURUSD=X", "BTC-USD")
        timeframe: Timeframe for candles
        limit: Number of candles to return (max 1000)
        
    Returns:
        Chart data with metadata and candles
        
    Example:
        GET /api/charts/candles/BTC-USD?timeframe=1d&limit=100
        
        Response:
        {
            "metadata": { ... },
            "candles": [
                {
                    "time": 1711933800,
                    "open": 10250.00,
                    "high": 10450.00,
                    "low": 10200.00,
                    "close": 10400.00,
                    "volume": 25000000
                },
                ...
            ],
            "timestamp": 1711933800,
            "cached": false
        }
    """
    try:
        # Validate timeframe
        try:
            TimeFrame(timeframe)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Valid: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo"
            )
        
        chart_service = get_chart_service()
        data = await chart_service.get_chart_data(symbol, timeframe, limit)
        
        return JSONResponse(data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting candles for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@ws_router.websocket("/charts/{symbol}")
async def websocket_chart_endpoint(websocket: WebSocket, symbol: str):
    """
    WebSocket endpoint for real-time chart updates.
    
    Args:
        websocket: WebSocket connection
        symbol: Forex/Crypto symbol (e.g., "EURUSD=X", "BTC-USD")
        
    Protocol:
    - Client sends "ping" → Server responds "pong" (keep-alive)
    - Client sends "update" → Server sends latest chart data
    - Server sends "candle_update" → New candle data (when available)
    
    Example (JavaScript):
        const ws = new WebSocket('ws://localhost:8000/ws/charts/BTC-USD');
        
        ws.onopen = () => {
            console.log('Connected');
            // Keep-alive ping every 30 seconds
            setInterval(() => ws.send('ping'), 30000);
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'candle_update') {
                updateChart(data.candle);
            } else {
                // Initial chart data
                renderChart(data);
            }
        };
        
        ws.onerror = (error) => console.error('WebSocket error:', error);
        ws.onclose = () => console.log('Disconnected');
    """
    try:
        chart_service = get_chart_service()
        await chart_service.subscribe_to_updates(websocket, symbol)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {symbol}")
    except Exception as e:
        logger.error(f"WebSocket error for {symbol}: {str(e)}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


@router.get("/trading-status")
async def get_trading_status():
    """
    Get current trading status.
    
    Returns:
        Trading status and next opening time
        
    Example:
        GET /api/charts/trading-status
        
        Response:
        {
            "is_trading": true,
            "next_open": 1711948800,
            "timezone": "Asia/Jakarta",
            "message": "Market is open (09:30-16:00 WIB)"
        }
    """
    try:
        chart_service = get_chart_service()
        is_trading = chart_service.is_trading_hours()
        next_open = chart_service.get_next_trading_time()
        
        if is_trading:
            message = "Forex market is open (24x5)"
        else:
            message = "Forex market is closed. Next open at 00:00 WIB"
        
        return JSONResponse({
            "is_trading": is_trading,
            "next_open": int(next_open.timestamp()),
            "timezone": "Asia/Jakarta",
            "message": message,
        })
    
    except Exception as e:
        logger.error(f"Error getting trading status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-symbols")
async def get_supported_symbols():
    """
    Get list of supported Forex/Crypto symbols.
    
    Returns:
        List of symbols with metadata
        
    Example:
        GET /api/charts/supported-symbols
        
        Response:
        [
            {
                "symbol": "EURUSD=X",
                "name": "EUR/USD",
                "sector": "Forex"
            },
            {
                "symbol": "BTC-USD",
                "name": "Bitcoin / US Dollar",
                "sector": "Crypto"
            },
            ...
        ]
    """
    try:
        symbols = []
        for symbol, info in MarketSymbolValidator.SYMBOLS.items():
            symbols.append({
                "symbol": symbol,
                "name": info.get("name", symbol),
                "sector": info.get("sector", "Unknown"),
                "minPrice": info.get("min_price", 0),
                "maxPrice": info.get("max_price", 0),
            })
        
        return JSONResponse(symbols)
    
    except Exception as e:
        logger.error(f"Error getting supported symbols: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Add routes to main app
def setup_chart_routes(app):
    """
    Setup chart routes to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    app.include_router(router)
    app.include_router(ws_router)
    logger.info("Chart routes configured")
