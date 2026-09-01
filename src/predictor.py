from pathlib import Path
import joblib
from .config import MODEL_DIR
from .preprocessing import clean_text, extract_location

class ComplaintPredictor:
    def __init__(self, model_dir: Path = MODEL_DIR):
        model_dir = Path(model_dir)
        self.category_vectorizer = joblib.load(model_dir / "category_vectorizer.joblib")
        self.category_model = joblib.load(model_dir / "category_model.joblib")
        self.priority_vectorizer = joblib.load(model_dir / "priority_vectorizer.joblib")
        self.priority_model = joblib.load(model_dir / "priority_model.joblib")

    def predict(self, complaint: str) -> dict:
        cleaned = clean_text(complaint)
        cx = self.category_vectorizer.transform([cleaned])
        px = self.priority_vectorizer.transform([cleaned])
        return {
            "category": self.category_model.predict(cx)[0],
            "category_confidence": float(max(self.category_model.predict_proba(cx)[0])),
            "priority": self.priority_model.predict(px)[0],
            "priority_confidence": float(max(self.priority_model.predict_proba(px)[0])),
            "location": extract_location(complaint),
        }
