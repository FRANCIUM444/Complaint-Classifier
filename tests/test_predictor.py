from src.predictor import ComplaintPredictor

def test_predictor_returns_expected_fields():
    predictor = ComplaintPredictor()
    result = predictor.predict("The fan in room 204 is not working.")
    assert {"category", "category_confidence", "priority", "priority_confidence", "location"} <= result.keys()
    assert 0 <= result["category_confidence"] <= 1
    assert 0 <= result["priority_confidence"] <= 1
    assert result["location"].lower() == "room 204"
