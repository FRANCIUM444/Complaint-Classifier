from src.preprocessing import clean_text, extract_location

def test_clean_text():
    assert clean_text("  FAN   NOT WORKING!!! ") == "fan not working!"

def test_extract_room():
    assert extract_location("Fan broken in room 204") == "room 204"
