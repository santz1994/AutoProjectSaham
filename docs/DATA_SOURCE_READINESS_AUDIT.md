# Data Source Readiness Audit

Date: 2026-04-06
Scope: ETL data connectors, feature engineering modules, validation and backtest support.

## Summary

The codebase already has strong coverage for core multimodal blocks:
- IDX market data and order-book capable integrations
- News sentiment feature extraction (VADER + optional FinBERT)
- Microstructure feature engineering (VWAP, OFI proxy, spread, impact)
- Purged time-series split and transaction-cost/slippage-aware backtesting

Main gap identified during this audit:
- No active COT (Commitment of Traders) connector in ETL flow

Implemented in this audit:
- Added COT connector using CFTC financial futures weekly data
- Integrated COT payload into ETL output with safe fallback
- Added connector and ETL integration unit tests

## Readiness Matrix

### Ready
- IDX connector and market data manager
- Feature store and microstructure module
- News sentiment module and NLP bridge
- Purged CV helper and training-time purged split support
- Backtest modules with commission and slippage controls

### Partial
- FinBERT is available but optional/off by default in runtime paths
- Forex connector available, but macro positioning feed was missing before this change

### Newly Added
- COT connector for macro positioning regime signals
- ETL key `cot` (and `cot_error` fallback)

## Files Updated in This Audit

- src/pipeline/data_connectors/cot_connector.py
- src/pipeline/etl.py
- tests/test_cot_connector.py
- tests/test_etl_cot_integration.py

## Validation

Targeted regression command:
- d:/Project/AutoSaham/.venv/Scripts/python.exe -m pytest tests/test_cot_connector.py tests/test_etl_cot_integration.py tests/test_pipeline_runner.py tests/test_forex_connector.py tests/test_news_connector.py -q

Result:
- 9 passed

## Next Engineering Priority

1. Build multimodal feature store schema to persist horizon-tagged features:
   - hft: microstructure and order-book derived metrics
   - intraday: technical plus sentiment aggregation
   - swing: broker flow and accumulation/distribution factors
   - macro: cot index and macro surprise ratios
2. Add economic calendar connector and surprise-ratio feature transforms.
3. Wire COT and macro features into training dataset assembly and model evaluation reports.
