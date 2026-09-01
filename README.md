# AI College Complaint Classifier

An end-to-end NLP/ML project for classifying college complaints, predicting urgency, extracting location, and finding similar previous complaints.

## Features
- Complaint category classification
- Priority prediction
- Location extraction
- Duplicate/similar complaint detection
- Streamlit web UI
- Scikit-learn training pipeline
- Demo dataset
- Unit tests
- Modular code

## Categories
Electrical, Cleanliness, Internet, Academic, Hostel, Security, Transport, Library, Food, Other

## Setup

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Install:
```bash
pip install -r requirements.txt
```

Train:
```bash
python -m src.train
```

Run:
```bash
streamlit run app/streamlit_app.py
```

## How it works

TF-IDF converts complaint text into numerical features. Logistic Regression predicts category and priority. Cosine similarity ranks similar previous complaints.

## Example

Input:
> The fan in room 204 has not been working for three days.

Output may include:
- Category: Electrical
- Priority: High
- Location: room 204
- Similar previous complaints

## GitHub

```bash
git init
git add .
git commit -m "Initial complaint classifier"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

## Future improvements
- 500–5000+ real anonymized labeled complaints
- Hindi/Hinglish support
- SQLite/PostgreSQL
- Admin dashboard
- FastAPI backend
- Transformer embeddings
- Authentication
- Email notifications
- Confusion matrix and model comparison
- Deployment

The included dataset is synthetic/demo data and is not production-grade.
