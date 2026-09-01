import re

def clean_text(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,!?/-]", "", text)
    return text

def extract_location(text: str) -> str:
    raw = str(text)
    patterns = [
        r"\b(room|rm)\s*[-#]?\s*[A-Za-z0-9-]+\b",
        r"\b(block|hostel|building|lab|library|canteen|cafeteria)\s*[A-Za-z0-9-]*\b",
        r"\b(gate|floor)\s*[-#]?\s*[A-Za-z0-9-]+\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.I)
        if match:
            return match.group(0)
    return "Not detected"
