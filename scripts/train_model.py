"""Train a baseline ML model from price history using sliding-window labels.

This script runs:
 - `src.ml.labeler.build_dataset`
 - `src.ml.trainer.train_model`

Example:
  python scripts/train_model.py --limit 50
"""
import argparse
import os

from src.ml.labeler import build_dataset
from src.ml.trainer import train_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--price-dir', default='data/prices')
    parser.add_argument('--out-dataset', default='data/dataset/dataset.csv')
    parser.add_argument('--model-out', default='models/model.joblib')
    parser.add_argument('--horizon', type=int, default=5)
    parser.add_argument('--threshold', type=float, default=0.02)
    parser.add_argument('--limit', type=int, default=50, help='Max symbols to include (useful for quick runs)')
    args = parser.parse_args()

    print('Building dataset...')
    ds = build_dataset(price_dir=args.price_dir, out_csv=args.out_dataset, horizon=args.horizon, threshold=args.threshold, max_symbols=args.limit)
    print('Dataset created at', ds)

    print('Training model...')
    res = train_model(ds, model_out=args.model_out)
    print('Model saved to', res.get('model_path'))
    print('ROC AUC:', res.get('roc_auc'))


if __name__ == '__main__':
    main()
