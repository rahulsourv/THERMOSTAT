from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


INPUT_FILE = Path("data/processed/ml_training_sample_2025.csv")
MODEL_FILE = Path("models/static_source_classifier_2025.joblib")

df = pd.read_csv(INPUT_FILE)

feature_columns = [
    "latitude",
    "longitude",
    "bright_ti4",
    "bright_ti5",
    "frp",
    "confidence",
    "month",
    "hour_utc",
    "is_night",
]

X = df[feature_columns]
y = df["static_source_label"]

numeric_features = [
    "latitude",
    "longitude",
    "bright_ti4",
    "bright_ti5",
    "frp",
    "month",
    "hour_utc",
    "is_night",
]

categorical_features = ["confidence"]

preprocessor = ColumnTransformer(
    transformers=[
        (
            "numeric",
            Pipeline(
                steps=[
                    ("imputer", SimpleImputer(strategy="median")),
                ]
            ),
            numeric_features,
        ),
        (
            "categorical",
            OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=False,
            ),
            categorical_features,
        ),
    ],
    sparse_threshold=0,
)

model = HistGradientBoostingClassifier(
    max_iter=150,
    learning_rate=0.1,
    max_leaf_nodes=31,
    random_state=42,
)

pipeline = Pipeline(
    steps=[
        ("preprocessor", preprocessor),
        ("model", model),
    ]
)

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,
)

print(f"Training examples: {len(X_train):,}")
print(f"Testing examples: {len(X_test):,}")

print("\nTraining model...")
pipeline.fit(X_train, y_train)

predictions = pipeline.predict(X_test)
probabilities = pipeline.predict_proba(X_test)[:, 1]

print("\nModel evaluation:")
print(classification_report(y_test, predictions))

print(
    "ROC-AUC:",
    round(roc_auc_score(y_test, probabilities), 4),
)

MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
joblib.dump(pipeline, MODEL_FILE)

print(f"\nSaved model to: {MODEL_FILE}")