"""Train PatchTST, MTST, and TFT transformer baselines.

Example:
  python scripts/train_transformer_baselines.py --epochs 5 --seq-len 32
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.labeler import build_dataset
from src.ml.transformer_baselines import train_transformer_baselines


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
        help="One or more architectures to train",
    )
    parser.add_argument("--model-dir", default="models/transformers")
    parser.add_argument("--report-out", default="models/transformers/baseline_report.json")
    parser.add_argument("--target-col", default="label")
    parser.add_argument("--seq-len", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--purge-gap", type=int, default=5)
    parser.add_argument("--patch-sizes", nargs="+", type=int, default=[4, 8, 16])
    parser.add_argument("--patch-stride", type=int, default=4)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    dataset_csv = args.dataset_csv
    if args.refresh_dataset or (not os.path.exists(dataset_csv)):
        print("Building dataset for transformer baselines...")
        dataset_csv = build_dataset(
            price_dir=args.price_dir,
            out_csv=dataset_csv,
            horizon=args.horizon,
            threshold=args.threshold,
            max_symbols=args.limit,
            include_multimodal=True,
            etl_dir=args.etl_dir,
        )

    print("Training transformer baselines...")
    summary = train_transformer_baselines(
        dataset_csv=dataset_csv,
        architectures=args.architectures,
        model_dir=args.model_dir,
        report_out=args.report_out,
        target_col=args.target_col,
        seq_len=args.seq_len,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        test_size=args.test_size,
        purge_gap=args.purge_gap,
        patch_sizes=args.patch_sizes,
        patch_stride=args.patch_stride,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        dropout=args.dropout,
        random_state=args.random_state,
        patience=args.patience,
        device=args.device,
    )

    print("\nBaseline training summary")
    for architecture, result in summary.get("results", {}).items():
        if result.get("error"):
            print(f"- {architecture}: FAILED ({result['error']})")
            continue
        metrics = result.get("metrics", {})
        print(
            f"- {architecture}: "
            f"acc={metrics.get('accuracy')} "
            f"f1_macro={metrics.get('f1_macro')} "
            f"auc={metrics.get('roc_auc_ovr_weighted')} "
            f"model={result.get('model_path')}"
        )

    if args.report_out:
        print(f"\nReport saved to {args.report_out}")


if __name__ == "__main__":
    main()
