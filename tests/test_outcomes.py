from decimal import Decimal
import pytest
from pydantic import ValidationError
from campus_assistant.api.seed import POLICY
from campus_assistant.outcomes import OutcomeInput, evaluate

def make(values):
    return OutcomeInput.model_validate({**POLICY, "assessments": [{**a, "score": values[i]} for i, a in enumerate(POLICY["assessments"])]})

def test_std003():
    result = evaluate(make([78, 52, 69]))
    assert [c["score"] for c in result["cpmks"]] == [78, 52, 69]
    assert [c["score"] for c in result["cpls"]] == [70.2, 64.4]
    assert [c["gap"] for c in result["cpmks"]] == [0, 23, 11]
    assert result["scope"] == "course_only"

def test_missing_not_zero():
    result = evaluate(make([58, None, 84]))
    assert result["cpmks"][1]["score"] is None
    assert all(c["score"] is None for c in result["cpls"])
    assert evaluate(make([58, 0, 84]))["cpmks"][1]["score"] == 0

def test_high_performer_and_invalid_input():
    assert all(c["status"] == "achieved" for c in evaluate(make([92, 90, 94]))["cpmks"])
    with pytest.raises(ValidationError):
        make([101, 50, 60])
    with pytest.raises(ValidationError):
        make([float('nan'), 50, 60])
    bad = make([1, 2, 3]).model_dump()
    bad["assessments"][0]["weight"] = Decimal("0.5")
    with pytest.raises(ValidationError):
        OutcomeInput.model_validate(bad)
