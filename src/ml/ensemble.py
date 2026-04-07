"""
Model Ensemble Implementation

Stacked ensemble combining multiple ML models for robust predictions:
- Level 1: LightGBM, XGBoost, RandomForest, LogisticRegression
- Level 2: Meta-model (Logistic Regression or LightGBM)

Features:
- Out-of-fold predictions to avoid overfitting
- Dynamic weight adjustment based on recent performance
- Model versioning and persistence
- A/B testing framework

Usage:
    from src.ml.ensemble import StackedEnsemble
    
    ensemble = StackedEnsemble()
    ensemble.fit(X_train, y_train)
    predictions = ensemble.predict_proba(X_test)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import joblib
import json
from datetime import datetime

# Base models
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

# Advanced models
try:
    from lightgbm import LGBMClassifier
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    LGBMClassifier = None

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    XGBClassifier = None


class StackedEnsemble:
    """
    Stacked ensemble classifier.
    
    Combines predictions from multiple base models using a meta-model.
    Uses out-of-fold predictions to prevent overfitting.
    """
    
    def __init__(
        self,
        n_folds: int = 5,
        use_lgbm: bool = True,
        use_xgb: bool = True,
        use_rf: bool = True,
        use_lr: bool = True,
        meta_model: str = 'logistic',
        random_state: int = 42,
        apply_oof_preprocessing: bool = True,
    ):
        """
        Initialize stacked ensemble.
        
        Args:
            n_folds: Number of folds for out-of-fold predictions
            use_lgbm: Include LightGBM in ensemble
            use_xgb: Include XGBoost in ensemble
            use_rf: Include RandomForest in ensemble
            use_lr: Include LogisticRegression in ensemble
            meta_model: Meta-model type ('logistic' or 'lgbm')
            random_state: Random seed
        """
        self.n_folds = n_folds
        self.random_state = random_state
        self.meta_model_type = meta_model
        self.apply_oof_preprocessing = bool(apply_oof_preprocessing)
        
        # Initialize base models
        self.base_models = {}
        self.model_names = []
        
        if use_lgbm and LIGHTGBM_AVAILABLE:
            self.base_models['lgbm'] = LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=6,
                num_leaves=31,
                random_state=random_state,
                verbose=-1
            )
            self.model_names.append('lgbm')
        
        if use_xgb and XGBOOST_AVAILABLE:
            self.base_models['xgb'] = XGBClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=6,
                random_state=random_state,
                eval_metric='logloss',
                use_label_encoder=False
            )
            self.model_names.append('xgb')
        
        if use_rf:
            self.base_models['rf'] = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=random_state,
                n_jobs=-1
            )
            self.model_names.append('rf')
        
        if use_lr:
            self.base_models['lr'] = LogisticRegression(
                max_iter=1000,
                random_state=random_state
            )
            self.model_names.append('lr')
        
        # Initialize meta-model
        if meta_model == 'logistic':
            self.meta_model = LogisticRegression(max_iter=1000, random_state=random_state)
        elif meta_model == 'lgbm' and LIGHTGBM_AVAILABLE:
            self.meta_model = LGBMClassifier(
                n_estimators=50,
                learning_rate=0.05,
                max_depth=3,
                random_state=random_state,
                verbose=-1
            )
        else:
            self.meta_model = LogisticRegression(max_iter=1000, random_state=random_state)
        
        # Fitted models storage (one per fold per base model)
        self.fitted_base_models = {name: [] for name in self.model_names}
        # Fold-specific preprocessors to avoid train/validation leakage.
        self.fitted_preprocessors = {name: [] for name in self.model_names}
        self.is_fitted = False
        
        # Performance tracking
        self.base_model_scores = {}
        self.meta_model_score = None
        
        # Dynamic weights
        self.model_weights = {name: 1.0 for name in self.model_names}

    def _build_fold_preprocessor(self):
        """Create a fold-scoped preprocessing pipeline."""
        return {
            'imputer': SimpleImputer(strategy='median'),
            'scaler': StandardScaler(),
        }
    
    def _get_oof_predictions(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Generate out-of-fold predictions for meta-model training.
        
        Args:
            X: Training features
            y: Training labels
            
        Returns:
            Tuple of (oof_predictions, base_predictions)
            - oof_predictions: Shape (n_samples, n_models)
            - base_predictions: Dict of model name -> predictions
        """
        n_samples = X.shape[0]
        n_models = len(self.model_names)
        
        # Initialize OOF predictions array
        oof_predictions = np.zeros((n_samples, n_models))
        base_predictions = {name: np.zeros(n_samples) for name in self.model_names}
        
        # K-Fold cross-validation
        kfold = KFold(n_splits=self.n_folds, shuffle=True, random_state=self.random_state)

        # Reset fitted state for retraining.
        self.fitted_base_models = {name: [] for name in self.model_names}
        self.fitted_preprocessors = {name: [] for name in self.model_names}
        
        for fold, (train_idx, val_idx) in enumerate(kfold.split(X)):
            X_train_fold = X[train_idx]
            y_train_fold = y[train_idx]
            X_val_fold = X[val_idx]
            
            # Train each base model
            for model_idx, model_name in enumerate(self.model_names):
                # Clone and fit model
                model = self.base_models[model_name]
                
                # Fit on fold training data
                if hasattr(model, 'fit'):
                    if self.apply_oof_preprocessing:
                        fold_preprocessor = self._build_fold_preprocessor()
                        imputer = fold_preprocessor['imputer']
                        scaler = fold_preprocessor['scaler']

                        X_train_fold_proc = imputer.fit_transform(X_train_fold)
                        X_train_fold_proc = scaler.fit_transform(X_train_fold_proc)

                        X_val_fold_proc = imputer.transform(X_val_fold)
                        X_val_fold_proc = scaler.transform(X_val_fold_proc)
                    else:
                        fold_preprocessor = None
                        X_train_fold_proc = X_train_fold
                        X_val_fold_proc = X_val_fold

                    fitted_model = model.__class__(**model.get_params())
                    fitted_model.fit(X_train_fold_proc, y_train_fold)
                    
                    # Store fitted model
                    self.fitted_base_models[model_name].append(fitted_model)
                    self.fitted_preprocessors[model_name].append(fold_preprocessor)
                    
                    # Predict on validation fold
                    if hasattr(fitted_model, 'predict_proba'):
                        preds = fitted_model.predict_proba(X_val_fold_proc)[:, 1]
                    else:
                        preds = fitted_model.predict(X_val_fold_proc)
                    
                    # Store OOF predictions
                    oof_predictions[val_idx, model_idx] = preds
                    base_predictions[model_name][val_idx] = preds
        
        return oof_predictions, base_predictions
    
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None
    ) -> 'StackedEnsemble':
        """
        Fit stacked ensemble.
        
        Args:
            X: Training features
            y: Training labels
            X_val: Validation features (optional)
            y_val: Validation labels (optional)
            
        Returns:
            Self
        """
        print(f"Training stacked ensemble with {len(self.model_names)} base models...")
        
        # Convert to numpy if needed
        if isinstance(X, pd.DataFrame):
            X = X.values
        if isinstance(y, pd.Series):
            y = y.values
        
        # Step 1: Generate out-of-fold predictions
        print("Step 1: Generating out-of-fold predictions...")
        oof_predictions, base_predictions = self._get_oof_predictions(X, y)
        
        # Step 2: Train meta-model on OOF predictions
        print("Step 2: Training meta-model...")
        self.meta_model.fit(oof_predictions, y)
        
        # Step 3: Calculate base model scores
        from sklearn.metrics import roc_auc_score
        
        for model_name in self.model_names:
            try:
                score = roc_auc_score(y, base_predictions[model_name])
                self.base_model_scores[model_name] = score
                print(f"  {model_name}: AUC = {score:.4f}")
            except Exception:
                self.base_model_scores[model_name] = 0.5
        
        # Step 4: Evaluate meta-model
        meta_preds = self.meta_model.predict_proba(oof_predictions)[:, 1]
        self.meta_model_score = roc_auc_score(y, meta_preds)
        print(f"  Meta-model: AUC = {self.meta_model_score:.4f}")
        
        # Update weights based on performance
        self._update_weights()
        
        self.is_fitted = True
        return self
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities.
        
        Args:
            X: Features
            
        Returns:
            Probability predictions (n_samples, 2)
        """
        if not self.is_fitted:
            raise ValueError("Ensemble not fitted yet. Call fit() first.")
        
        # Convert to numpy if needed
        if isinstance(X, pd.DataFrame):
            X = X.values
        
        # Get predictions from all base models (average across folds)
        n_samples = X.shape[0]
        n_models = len(self.model_names)
        base_predictions = np.zeros((n_samples, n_models))
        
        for model_idx, model_name in enumerate(self.model_names):
            # Average predictions across all folds
            fold_predictions = []
            model_folds = self.fitted_base_models[model_name]
            model_preprocessors = self.fitted_preprocessors.get(model_name, [])

            for fold_idx, fitted_model in enumerate(model_folds):
                X_proc = X
                if self.apply_oof_preprocessing and fold_idx < len(model_preprocessors):
                    fold_preprocessor = model_preprocessors[fold_idx]
                    if fold_preprocessor is not None:
                        X_proc = fold_preprocessor['imputer'].transform(X_proc)
                        X_proc = fold_preprocessor['scaler'].transform(X_proc)

                if hasattr(fitted_model, 'predict_proba'):
                    preds = fitted_model.predict_proba(X_proc)[:, 1]
                else:
                    preds = fitted_model.predict(X_proc)
                fold_predictions.append(preds)
            
            # Average across folds
            base_predictions[:, model_idx] = np.mean(fold_predictions, axis=0)
        
        # Meta-model prediction
        meta_proba = self.meta_model.predict_proba(base_predictions)
        
        return meta_proba
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class labels.
        
        Args:
            X: Features
            
        Returns:
            Class predictions (n_samples,)
        """
        proba = self.predict_proba(X)
        return (proba[:, 1] >= 0.5).astype(int)
    
    def _update_weights(self) -> None:
        """Update model weights based on performance."""
        # Baseline-adjusted weighting: AUC=0.5 carries no predictive edge.
        adjusted_scores = {
            model_name: max(0.0, float(self.base_model_scores.get(model_name, 0.0)) - 0.5)
            for model_name in self.model_names
        }
        total_score = sum(adjusted_scores.values())
        
        if total_score > 0:
            for model_name in self.model_names:
                self.model_weights[model_name] = adjusted_scores[model_name] / total_score
        else:
            # Equal weights if all models are near random baseline.
            for model_name in self.model_names:
                self.model_weights[model_name] = 1.0 / len(self.model_names)
    
    def get_model_importance(self) -> pd.DataFrame:
        """
        Get model importance scores.
        
        Returns:
            DataFrame with model scores and weights
        """
        return pd.DataFrame({
            'model': self.model_names,
            'auc_score': [self.base_model_scores.get(name, 0) for name in self.model_names],
            'weight': [self.model_weights.get(name, 0) for name in self.model_names]
        }).sort_values('auc_score', ascending=False)
    
    def save(self, filepath: str) -> None:
        """
        Save ensemble to file.
        
        Args:
            filepath: Path to save file
        """
        save_dir = Path(filepath).parent
        save_dir.mkdir(parents=True, exist_ok=True)
        
        ensemble_data = {
            'fitted_base_models': self.fitted_base_models,
            'fitted_preprocessors': self.fitted_preprocessors,
            'meta_model': self.meta_model,
            'model_names': self.model_names,
            'base_model_scores': self.base_model_scores,
            'meta_model_score': self.meta_model_score,
            'model_weights': self.model_weights,
            'is_fitted': self.is_fitted,
            'metadata': {
                'n_folds': self.n_folds,
                'meta_model_type': self.meta_model_type,
                'apply_oof_preprocessing': self.apply_oof_preprocessing,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        joblib.dump(ensemble_data, filepath)
        print(f"Ensemble saved to {filepath}")
    
    def load(self, filepath: str) -> None:
        """
        Load ensemble from file.
        
        Args:
            filepath: Path to load file
        """
        ensemble_data = joblib.load(filepath)
        
        self.fitted_base_models = ensemble_data['fitted_base_models']
        self.fitted_preprocessors = ensemble_data.get('fitted_preprocessors', {})
        self.meta_model = ensemble_data['meta_model']
        self.model_names = ensemble_data['model_names']
        self.base_model_scores = ensemble_data['base_model_scores']
        self.meta_model_score = ensemble_data['meta_model_score']
        self.model_weights = ensemble_data['model_weights']
        self.is_fitted = ensemble_data['is_fitted']

        metadata = ensemble_data.get('metadata', {})
        self.apply_oof_preprocessing = bool(
            metadata.get('apply_oof_preprocessing', self.apply_oof_preprocessing)
        )

        for model_name in self.model_names:
            if model_name not in self.fitted_preprocessors:
                self.fitted_preprocessors[model_name] = [None] * len(
                    self.fitted_base_models.get(model_name, [])
                )
        
        print(f"Ensemble loaded from {filepath}")
        print(f"Meta-model AUC: {self.meta_model_score:.4f}")


# Example usage
if __name__ == "__main__":
    from sklearn.datasets import make_classification
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, classification_report
    
    print("=== Stacked Ensemble Example ===\n")
    
    # Generate synthetic data
    X, y = make_classification(
        n_samples=1000,
        n_features=20,
        n_informative=15,
        n_redundant=5,
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    
    # Create and train ensemble
    ensemble = StackedEnsemble(
        n_folds=5,
        use_lgbm=LIGHTGBM_AVAILABLE,
        use_xgb=XGBOOST_AVAILABLE,
        use_rf=True,
        use_lr=True
    )
    
    ensemble.fit(X_train, y_train)
    
    # Make predictions
    y_pred_proba = ensemble.predict_proba(X_test)[:, 1]
    y_pred = ensemble.predict(X_test)
    
    # Evaluate
    auc = roc_auc_score(y_test, y_pred_proba)
    
    print(f"\n=== Test Set Performance ===")
    print(f"AUC: {auc:.4f}")
    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred))
    
    # Model importance
    print(f"\n=== Model Importance ===")
    print(ensemble.get_model_importance())
    
    # Save ensemble
    ensemble.save('models/ensemble_test.joblib')
    print("\n✓ Ensemble saved successfully")
