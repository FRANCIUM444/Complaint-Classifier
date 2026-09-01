import sys
from pathlib import Path
import joblib
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DATA_PATH, MODEL_DIR
from src.predictor import ComplaintPredictor
from src.similarity import find_similar

st.set_page_config(page_title="AI Complaint Classifier", page_icon="🎓", layout="wide")
st.title("🎓 AI College Complaint Classifier")
st.caption("NLP + Machine Learning + Similarity Search")

@st.cache_resource
def load_predictor():
    return ComplaintPredictor()

@st.cache_resource
def load_vectorizer():
    return joblib.load(MODEL_DIR / "category_vectorizer.joblib")

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)

try:
    predictor = load_predictor()
    vectorizer = load_vectorizer()
    df = load_data()
except FileNotFoundError:
    st.error("Models are missing. Run: python -m src.train")
    st.stop()

with st.sidebar:
    st.header("Project")
    st.write("Classifies college complaints and estimates urgency.")
    st.write("Categories: " + ", ".join(sorted(df.category.unique())))
    st.write("Priority: Low • Medium • High")

complaint = st.text_area(
    "Enter a complaint",
    placeholder="The fan in room 204 has not been working for three days.",
    height=150,
)

if st.button("Analyze Complaint", type="primary", use_container_width=True):
    if not complaint.strip():
        st.warning("Please enter a complaint.")
    else:
        result = predictor.predict(complaint)
        c1, c2, c3 = st.columns(3)
        c1.metric("Category", result["category"])
        c2.metric("Priority", result["priority"])
        c3.metric("Location", result["location"])

        st.subheader("Model confidence")
        conf = pd.DataFrame({
            "Prediction": ["Category", "Priority"],
            "Confidence": [result["category_confidence"], result["priority_confidence"]]
        }).set_index("Prediction")
        st.bar_chart(conf)

        st.subheader("Similar previous complaints")
        similar = find_similar(complaint, df, vectorizer, 5)
        st.dataframe(
            similar[["complaint", "category", "priority", "location", "similarity"]],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.subheader("📊 Dataset overview")
a, b, c = st.columns(3)
a.metric("Complaints", len(df))
b.metric("Categories", df.category.nunique())
c.metric("High priority", int((df.priority == "High").sum()))
st.bar_chart(df["category"].value_counts())
