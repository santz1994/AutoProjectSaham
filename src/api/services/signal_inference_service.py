"""Signal generation helpers for transformer inference and technical fallback paths."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional


def _resolve_regime_overlay(route: Any) -> Optional[Callable[..., Any]]:
    if route is None:
        return None
    try:
        from src.ml.regime_router import apply_regime_overlay

        return apply_regime_overlay
    except Exception:
        return None


def infer_signals_from_transformer(
    limit: int,
    preferred_universe: Optional[List[str]],
    *,
    resolve_dataset_csv_path_fn: Callable[[], str],
    load_transformer_runtime_fn: Callable[[], Optional[Dict[str, Any]]],
    resolve_signal_universe_fn: Callable[[Any, Optional[List[str]], int], List[str]],
    resolve_regime_route_fn: Callable[[Any, Optional[List[str]]], Optional[Any]],
    build_symbol_sequences_fn: Callable[..., List[Dict[str, Any]]],
    estimate_label_returns_fn: Callable[[Any], Dict[int, float]],
    signal_from_expected_return_fn: Callable[[float, float, List[float]], str],
    symbol_name_fn: Callable[[str], str],
    risk_level_from_prediction_fn: Callable[[float, float], str],
    symbol_sector_fn: Callable[[str], str],
    signal_model_cls: Any,
    datetime_now_fn: Callable[[], Any],
) -> List[Any]:
    import numpy as np

    safe_limit = max(1, int(limit))
    dataset_csv = resolve_dataset_csv_path_fn()
    if not os.path.exists(dataset_csv):
        return []

    runtime = load_transformer_runtime_fn()
    if runtime is None:
        return []

    try:
        import pandas as pd
        import torch

        df = pd.read_csv(dataset_csv)
        if df.empty or "symbol" not in df.columns:
            return []

        symbols = resolve_signal_universe_fn(df, preferred_universe, max(safe_limit * 3, 6))
        if not symbols:
            return []

        regime_route = resolve_regime_route_fn(df, symbols)
        regime_overlay_fn = _resolve_regime_overlay(regime_route)

        samples = build_symbol_sequences_fn(
            df,
            feature_columns=runtime["feature_columns"],
            seq_len=int(runtime["seq_len"]),
            symbols=symbols,
        )
        if not samples:
            return []

        x = np.stack([item["sequence"] for item in samples], axis=0).astype(np.float32)
        mean = runtime["normalization_mean"]
        std = runtime["normalization_std"]
        if mean.shape[-1] != x.shape[-1] or std.shape[-1] != x.shape[-1]:
            mean = np.zeros((1, 1, x.shape[-1]), dtype=np.float32)
            std = np.ones((1, 1, x.shape[-1]), dtype=np.float32)

        normalized = ((x - mean) / std).astype(np.float32)
        tensor = torch.tensor(normalized, dtype=torch.float32)

        with torch.no_grad():
            logits = runtime["model"](tensor)
            probs = torch.softmax(logits, dim=1).cpu().numpy()

        label_returns = estimate_label_returns_fn(df)
        return_levels = list(label_returns.values())
        generated_at = datetime_now_fn().isoformat()
        ranked_rows: List[Dict[str, Any]] = []

        for index, sample in enumerate(samples):
            probabilities = probs[index]
            pred_idx = int(np.argmax(probabilities))
            confidence = float(np.max(probabilities))

            predicted_label = runtime["index_to_label"].get(pred_idx, pred_idx)
            try:
                predicted_label_int = int(predicted_label)
            except Exception:
                predicted_label_int = pred_idx

            expected_return = float(label_returns.get(predicted_label_int, 0.0))
            signal_name = signal_from_expected_return_fn(expected_return, confidence, return_levels)

            regime_note = ""
            if regime_overlay_fn is not None and regime_route is not None:
                signal_name, expected_return, regime_note = regime_overlay_fn(
                    signal=signal_name,
                    expected_return=expected_return,
                    model_confidence=confidence,
                    route=regime_route,
                )

            current_price = float(sample["current_price"])
            target_price = current_price * (1.0 + expected_return) if current_price > 0 else 0.0

            base_reason = (
                f"{str(runtime['architecture']).upper()} model ({runtime['source']}) "
                f"predicted class {predicted_label_int} with {confidence * 100:.1f}% confidence."
            )
            if regime_note:
                base_reason = f"{base_reason} {regime_note}"

            ranked_rows.append(
                {
                    "rank": confidence * (abs(expected_return) + 0.001),
                    "symbol": sample["symbol"],
                    "name": symbol_name_fn(sample["symbol"]),
                    "signal": signal_name,
                    "confidence": confidence,
                    "reason": base_reason,
                    "predictedMove": f"{expected_return * 100:+.2f}%",
                    "riskLevel": risk_level_from_prediction_fn(expected_return, confidence),
                    "sector": symbol_sector_fn(sample["symbol"]),
                    "currentPrice": current_price,
                    "targetPrice": float(max(0.0, target_price)),
                    "timestamp": generated_at,
                }
            )

        ranked_rows.sort(key=lambda item: item["rank"], reverse=True)

        return [
            signal_model_cls(
                id=rank,
                symbol=row["symbol"],
                name=row["name"],
                signal=row["signal"],
                confidence=row["confidence"],
                reason=row["reason"],
                predictedMove=row["predictedMove"],
                riskLevel=row["riskLevel"],
                sector=row["sector"],
                currentPrice=row["currentPrice"],
                targetPrice=row["targetPrice"],
                timestamp=row["timestamp"],
            )
            for rank, row in enumerate(ranked_rows[:safe_limit], start=1)
        ]
    except Exception:
        return []


def build_fallback_signals(
    limit: int,
    preferred_universe: Optional[List[str]],
    *,
    resolve_dataset_csv_path_fn: Callable[[], str],
    resolve_signal_universe_fn: Callable[[Any, Optional[List[str]], int], List[str]],
    resolve_regime_route_fn: Callable[[Any, Optional[List[str]]], Optional[Any]],
    signal_from_expected_return_fn: Callable[[float, float, List[float]], str],
    safe_float_fn: Callable[[Any, Optional[float]], Optional[float]],
    symbol_name_fn: Callable[[str], str],
    risk_level_from_prediction_fn: Callable[[float, float], str],
    symbol_sector_fn: Callable[[str], str],
    signal_model_cls: Any,
    datetime_now_fn: Callable[[], Any],
) -> List[Any]:
    safe_limit = max(1, int(limit))
    dataset_csv = resolve_dataset_csv_path_fn()

    try:
        import pandas as pd

        if os.path.exists(dataset_csv):
            df = pd.read_csv(dataset_csv)
            if (not df.empty) and ("symbol" in df.columns):
                symbols = resolve_signal_universe_fn(df, preferred_universe, max(safe_limit * 3, 6))
                generated_at = datetime_now_fn().isoformat()
                rows: List[Dict[str, Any]] = []

                regime_route = resolve_regime_route_fn(df, symbols)
                regime_overlay_fn = _resolve_regime_overlay(regime_route)

                for symbol in symbols:
                    symbol_df = df[df["symbol"].astype(str) == str(symbol)]
                    if symbol_df.empty:
                        continue
                    last_row = symbol_df.iloc[-1]

                    momentum = safe_float_fn(last_row.get("momentum"), default=0.0) or 0.0
                    short_sma = safe_float_fn(last_row.get("short_sma"), default=0.0) or 0.0
                    long_sma = safe_float_fn(last_row.get("long_sma"), default=0.0) or 0.0
                    current_price = safe_float_fn(last_row.get("last_price"), default=0.0) or 0.0

                    trend_gap = ((short_sma - long_sma) / long_sma) if long_sma > 0 else 0.0
                    expected_return = max(-0.08, min(0.08, (0.6 * momentum) + (0.4 * trend_gap)))
                    confidence = max(0.50, min(0.85, 0.55 + (abs(expected_return) * 4.0)))
                    signal_name = signal_from_expected_return_fn(
                        expected_return,
                        confidence,
                        return_levels=[-abs(expected_return), abs(expected_return)],
                    )

                    regime_note = ""
                    if regime_overlay_fn is not None and regime_route is not None:
                        signal_name, expected_return, regime_note = regime_overlay_fn(
                            signal=signal_name,
                            expected_return=expected_return,
                            model_confidence=confidence,
                            route=regime_route,
                        )

                    base_reason = (
                        "Fallback technical heuristic using momentum and SMA trend gap "
                        "while transformer signal model is unavailable."
                    )
                    if regime_note:
                        base_reason = f"{base_reason} {regime_note}"

                    rows.append(
                        {
                            "rank": confidence * (abs(expected_return) + 0.001),
                            "symbol": str(symbol),
                            "name": symbol_name_fn(str(symbol)),
                            "signal": signal_name,
                            "confidence": confidence,
                            "reason": base_reason,
                            "predictedMove": f"{expected_return * 100:+.2f}%",
                            "riskLevel": risk_level_from_prediction_fn(expected_return, confidence),
                            "sector": symbol_sector_fn(str(symbol)),
                            "currentPrice": float(max(0.0, current_price)),
                            "targetPrice": float(max(0.0, current_price * (1.0 + expected_return))),
                            "timestamp": generated_at,
                        }
                    )

                rows.sort(key=lambda item: item["rank"], reverse=True)
                if rows:
                    return [
                        signal_model_cls(
                            id=index,
                            symbol=item["symbol"],
                            name=item["name"],
                            signal=item["signal"],
                            confidence=item["confidence"],
                            reason=item["reason"],
                            predictedMove=item["predictedMove"],
                            riskLevel=item["riskLevel"],
                            sector=item["sector"],
                            currentPrice=item["currentPrice"],
                            targetPrice=item["targetPrice"],
                            timestamp=item["timestamp"],
                        )
                        for index, item in enumerate(rows[:safe_limit], start=1)
                    ]
    except Exception:
        pass

    return [
        signal_model_cls(
            id=1,
            symbol="EURUSD=X",
            name="EUR/USD",
            signal="HOLD",
            confidence=0.5,
            reason="No valid model output is available yet; fallback signal is neutral.",
            predictedMove="+0.00%",
            riskLevel="Medium",
            sector="Forex",
            currentPrice=1.0,
            targetPrice=1.0,
            timestamp=datetime_now_fn().isoformat(),
        )
    ][:safe_limit]
