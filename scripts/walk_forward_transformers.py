"""Run walk-forward evaluation for transformer architectures.

Example:
  python scripts/walk_forward_transformers.py --epochs 2 --max-folds 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.labeler import build_dataset
from src.ml.walk_forward import evaluate_transformer_walk_forward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-csv", default="data/dataset/dataset.csv")
    parser.add_argument("--refresh-dataset", action="store_true")
    parser.add_argument("--price-dir", default="data/prices")
    parser.add_argument("--etl-dir", default="data")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.02)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--architectures",
        nargs="+",
        default=["patchtst", "mtst", "tft", "fusion"],
        help="One or more architectures to evaluate",
    )
    parser.add_argument("--target-col", default="label")
    parser.add_argument("--seq-len", type=int, default=32)
    parser.add_argument("--min-train-size", type=int, default=300)
    parser.add_argument("--fold-test-size", type=int, default=100)
    parser.add_argument("--step-size", type=int, default=None)
    parser.add_argument("--purge-gap", type=int, default=5)
    parser.add_argument("--val-size", type=float, default=0.1)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--patch-sizes", nargs="+", type=int, default=[4, 8, 16])
    parser.add_argument("--patch-stride", type=int, default=4)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--device", default=None)
    parser.add_argument("--expanding", action="store_true")
    parser.add_argument("--max-folds", type=int, default=None)
    parser.add_argument("--model-dir", default="models/transformers/walk_forward")
    parser.add_argument("--report-out", default="models/transformers/walk_forward_report.json")
    args = parser.parse_args()

    dataset_csv = args.dataset_csv
    if args.refresh_dataset or (not os.path.exists(dataset_csv)):
        print("Building dataset for walk-forward evaluation...")
        dataset_csv = build_dataset(
            price_dir=args.price_dir,
            out_csv=dataset_csv,
            horizon=args.horizon,
            threshold=args.threshold,
            max_symbols=args.limit,
            include_multimodal=True,
            etl_dir=args.etl_dir,
        )

    os.makedirs(args.model_dir, exist_ok=True)
    combined = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "dataset_csv": dataset_csv,
        "architectures": args.architectures,
        "results": {},
    }

    for architecture in args.architectures:
        print(f"Running walk-forward evaluation: {architecture}")
        architecture_model_dir = os.path.join(args.model_dir, architecture.lower())
        result = evaluate_transformer_walk_forward(
            dataset_csv=dataset_csv,
            architecture=architecture,
            target_col=args.target_col,
            seq_len=args.seq_len,
            min_train_size=args.min_train_size,
            fold_test_size=args.fold_test_size,
            step_size=args.step_size,
            purge_gap=args.purge_gap,
            val_size=args.val_size,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            patch_sizes=args.patch_sizes,
            patch_stride=args.patch_stride,
            d_model=args.d_model,
            n_heads=args.n_heads,
            n_layers=args.n_layers,
            dropout=args.dropout,
            random_state=args.random_state,
            device=args.device,
            patience=args.patience,
            expanding=args.expanding,
            max_folds=args.max_folds,
            model_dir=architecture_model_dir,
            report_out=None,
        )
        combined["results"][architecture.lower()] = result

        aggregate = result.get("aggregate", {})
        print(
            f"- {architecture}: "
            f"folds={result.get('successful_folds')}/{result.get('fold_count')} "
            f"acc_mean={aggregate.get('accuracy_mean')} "
            f"f1_macro_mean={aggregate.get('f1_macro_mean')}"
        )

    if args.report_out:
        os.makedirs(os.path.dirname(args.report_out) or ".", exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as handle:
            json.dump(combined, handle, indent=2)
        print(f"\nCombined report saved to {args.report_out}")


if __name__ == "__main__":
    main()
