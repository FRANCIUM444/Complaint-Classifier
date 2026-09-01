import json
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from .config import DATA_PATH, MODEL_DIR
from .preprocessing import clean_text

def main():
    MODEL_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(DATA_PATH).dropna()
    df["text_clean"] = df["complaint"].map(clean_text)
    metrics = {}

    for target in ["category", "priority"]:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1,
                                      max_df=0.98, sublinear_tf=True)
        X = vectorizer.fit_transform(df["text_clean"])
        y = df[target]

        if len(df) >= 30 and y.nunique() > 1:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            eval_model = LogisticRegression(max_iter=2000, class_weight="balanced")
            eval_model.fit(X_train, y_train)
            pred = eval_model.predict(X_test)
            metrics[target] = {
                "accuracy": round(float(accuracy_score(y_test, pred)), 4),
                "report": classification_report(
                    y_test, pred, output_dict=True, zero_division=0
                ),
            }

        final_model = LogisticRegression(max_iter=2000, class_weight="balanced")
        final_model.fit(X, y)
        joblib.dump(vectorizer, MODEL_DIR / f"{target}_vectorizer.joblib")
        joblib.dump(final_model, MODEL_DIR / f"{target}_model.joblib")

    (MODEL_DIR / "metadata.json").write_text(
        json.dumps({
            "dataset_rows": int(len(df)),
            "categories": sorted(df["category"].unique().tolist()),
            "priorities": sorted(df["priority"].unique().tolist()),
            "metrics": metrics
        }, indent=2),
        encoding="utf-8"
    )
    print(f"Trained models using {len(df)} complaints.")
    for target, result in metrics.items():
        print(f"{target} accuracy: {result['accuracy']}")

if __name__ == "__main__":
    main()
