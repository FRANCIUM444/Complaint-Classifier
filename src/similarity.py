import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from .preprocessing import clean_text

def find_similar(complaint: str, df: pd.DataFrame, vectorizer, top_k: int = 5):
    if df.empty:
        return pd.DataFrame()
    query = vectorizer.transform([clean_text(complaint)])
    corpus = vectorizer.transform(df["complaint"].map(clean_text))
    scores = cosine_similarity(query, corpus).ravel()
    result = df.copy()
    result["similarity"] = scores
    return result.sort_values("similarity", ascending=False).head(top_k).assign(
        similarity=lambda x: x["similarity"].round(3)
    )
