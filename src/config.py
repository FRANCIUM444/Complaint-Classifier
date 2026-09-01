from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT_DIR / "data" / "complaints.csv"
MODEL_DIR = ROOT_DIR / "models"
