"""COT (Commitment of Traders) connector for macro regime features.

Fetches weekly CFTC financial futures positioning and computes a normalized
COT Index (0-100) from non-commercial and commercial net positions.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_COT_URL = "https://www.cftc.gov/dea/newcot/FinFutWk.txt"

# Aliases tuned for common FX macro pairs.
MARKET_ALIASES: Dict[str, List[str]] = {
    "EURUSD": ["EURO FX", "EUR"],
    "GBPUSD": ["BRITISH POUND", "GBP"],
    "USDJPY": ["JAPANESE YEN", "JPY"],
    "AUDUSD": ["AUSTRALIAN DOLLAR", "AUD"],
    "USDCAD": ["CANADIAN DOLLAR", "CAD"],
    "USDCHF": ["SWISS FRANC", "CHF"],
    "NZDUSD": ["NEW ZEALAND DOLLAR", "NZD"],
    "DXY": ["US DOLLAR INDEX", "USD INDEX"],
}


def _norm_key(value: str) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _pick_field(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[Any]:
    if not isinstance(row, dict):
        return None

    items = {str(k): v for k, v in row.items()}
    normalized = {_norm_key(k): v for k, v in items.items()}

    # Exact normalized key match first.
    for candidate in candidates:
        key = _norm_key(candidate)
        if key in normalized:
            return normalized[key]

    # Then substring match on normalized names.
    for candidate in candidates:
        key = _norm_key(candidate)
        for existing, value in normalized.items():
            if key in existing:
                return value

    return None


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A", "NULL", "NONE", "-"}:
        return None

    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"

    text = text.replace(",", "").replace("%", "")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%Y%m%d",
        "%y%m%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _rows_from_response_text(payload_text: str) -> List[Dict[str, Any]]:
    if not payload_text.strip():
        return []

    sample = payload_text[:2048]
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(payload_text), delimiter=delimiter)
    return [dict(row) for row in reader]


def _rolling_index(values: List[float], window: int) -> List[float]:
    out: List[float] = []
    for idx, val in enumerate(values):
        left = max(0, idx - window + 1)
        segment = values[left : idx + 1]
        low = min(segment)
        high = max(segment)
        if high == low:
            out.append(50.0)
        else:
            out.append((val - low) / (high - low) * 100.0)
    return out


def _match_alias(market_name: str, aliases: List[str]) -> bool:
    upper = market_name.upper()
    return any(alias.upper() in upper for alias in aliases)


def fetch_cot_data(
    market: str = "EURUSD",
    lookback_weeks: int = 26,
    source_url: str = DEFAULT_COT_URL,
) -> Dict[str, Any]:
    """Fetch and normalize weekly COT data for one market.

    Args:
        market: Macro market key (e.g. EURUSD, GBPUSD, DXY).
        lookback_weeks: Rolling window used for COT Index normalization.
        source_url: CFTC COT source endpoint.

    Returns:
        Dict with normalized records and latest snapshot.

    Raises:
        RuntimeError: If source parsing or normalization fails.
    """
    if lookback_weeks < 2:
        raise ValueError("lookback_weeks must be >= 2")

    try:
        import requests  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "requests not installed; install with `pip install requests`"
        ) from exc

    response = requests.get(source_url, timeout=20)
    response.raise_for_status()

    records = _rows_from_response_text(response.text)
    if not records:
        raise RuntimeError("COT payload could not be parsed into rows")

    market_key = str(market or "").strip().upper()
    aliases = MARKET_ALIASES.get(market_key, [market_key])

    normalized_rows: List[Dict[str, Any]] = []
    for row in records:
        market_name = _pick_field(
            row,
            [
                "Market_and_Exchange_Names",
                "market_and_exchange_names",
                "market",
                "market_name",
            ],
        )
        if not market_name:
            continue

        market_name_text = str(market_name)
        if not _match_alias(market_name_text, aliases):
            continue

        report_date = _parse_date(
            _pick_field(
                row,
                [
                    "Report_Date_as_YYYY-MM-DD",
                    "As_of_Date_In_Form_YYMMDD",
                    "Report_Date_as_MM_DD_YYYY",
                    "report_date",
                    "date",
                ],
            )
        )

        noncomm_long = _parse_float(
            _pick_field(
                row,
                [
                    "Noncommercial_Positions_Long_All",
                    "noncommercial_long",
                    "noncommercialpositionslongall",
                    "noncommercial long",
                ],
            )
        )
        noncomm_short = _parse_float(
            _pick_field(
                row,
                [
                    "Noncommercial_Positions_Short_All",
                    "noncommercial_short",
                    "noncommercialpositionsshortall",
                    "noncommercial short",
                ],
            )
        )

        commercial_long = _parse_float(
            _pick_field(
                row,
                [
                    "Commercial_Positions_Long_All",
                    "commercial_long",
                    "commercialpositionslongall",
                    "commercial long",
                ],
            )
        )
        commercial_short = _parse_float(
            _pick_field(
                row,
                [
                    "Commercial_Positions_Short_All",
                    "commercial_short",
                    "commercialpositionsshortall",
                    "commercial short",
                ],
            )
        )

        if (
            report_date is None
            or noncomm_long is None
            or noncomm_short is None
            or commercial_long is None
            or commercial_short is None
        ):
            continue

        normalized_rows.append(
            {
                "date": report_date,
                "market_name": market_name_text,
                "noncommercial_long": float(noncomm_long),
                "noncommercial_short": float(noncomm_short),
                "commercial_long": float(commercial_long),
                "commercial_short": float(commercial_short),
            }
        )

    if not normalized_rows:
        raise RuntimeError(f"No COT rows matched market={market_key}")

    normalized_rows.sort(key=lambda item: item["date"])

    noncomm_net = [
        row["noncommercial_long"] - row["noncommercial_short"]
        for row in normalized_rows
    ]
    comm_net = [
        row["commercial_long"] - row["commercial_short"]
        for row in normalized_rows
    ]

    noncomm_index = _rolling_index(noncomm_net, int(lookback_weeks))
    comm_index = _rolling_index(comm_net, int(lookback_weeks))

    for idx, row in enumerate(normalized_rows):
        row["noncommercial_net"] = float(noncomm_net[idx])
        row["commercial_net"] = float(comm_net[idx])
        row["cot_index_noncommercial"] = float(noncomm_index[idx])
        row["cot_index_commercial"] = float(comm_index[idx])

    latest = normalized_rows[-1]

    return {
        "market": market_key,
        "source": source_url,
        "lookback_weeks": int(lookback_weeks),
        "records": normalized_rows,
        "latest": latest,
        "n_records": len(normalized_rows),
    }
