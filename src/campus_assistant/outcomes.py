"""Deterministic course-scoped outcomes. Missing scores are never zero."""
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field, model_validator

class AssessmentInput(BaseModel):
    id: str
    cpmk_id: str
    weight: Decimal = Field(gt=0, le=1)
    score: Decimal | None = Field(default=None, ge=0, le=100)

class CPMKInput(BaseModel):
    id: str
    target: Decimal = Field(ge=0, le=100)
    cpl_mapping: dict[str, Decimal]

class OutcomeInput(BaseModel):
    assessments: list[AssessmentInput]
    cpmks: list[CPMKInput]
    cpl_targets: dict[str, Decimal]

    @model_validator(mode="after")
    def validate_mapping(self):
        if not self.cpmks or len({c.id for c in self.cpmks}) != len(self.cpmks):
            raise ValueError("CPMK IDs must be nonempty and unique")
        if len({a.id for a in self.assessments}) != len(self.assessments):
            raise ValueError("Assessment IDs must be unique")
        ids = {c.id for c in self.cpmks}
        if any(a.cpmk_id not in ids for a in self.assessments):
            raise ValueError("Unknown CPMK")
        for c in self.cpmks:
            if sum(a.weight for a in self.assessments if a.cpmk_id == c.id) != Decimal(1):
                raise ValueError("Assessment weights per CPMK must sum to one")
            if not c.cpl_mapping or sum(c.cpl_mapping.values()) != Decimal(1):
                raise ValueError("CPMK outgoing CPL weights must sum to one")
            if any(k not in self.cpl_targets or not v.is_finite() or v <= 0 for k, v in c.cpl_mapping.items()):
                raise ValueError("Invalid CPL mapping")
        if any(not v.is_finite() or v < 0 or v > 100 for v in self.cpl_targets.values()):
            raise ValueError("Invalid CPL target")
        if any(not any(k in c.cpl_mapping for c in self.cpmks) for k in self.cpl_targets):
            raise ValueError("Unmapped CPL")
        return self


def evaluate(data: OutcomeInput) -> dict:
    def number(v):
        return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if v is not None else None
    cpmks = []
    raw = {}
    for c in data.cpmks:
        evidence = [a for a in data.assessments if a.cpmk_id == c.id]
        complete = all(a.score is not None for a in evidence)
        score = sum(a.score * a.weight for a in evidence) if complete else None
        raw[c.id] = score
        gap = max(Decimal(0), c.target - score) if complete else None
        cpmks.append({"id": c.id, "score": number(score), "target": number(c.target),
                      "gap": number(gap), "status": "incomplete" if not complete else "gap" if gap > 0 else "achieved",
                      "evidence_ids": [a.id for a in evidence], "complete": complete})
    cpls = []
    for key, target in data.cpl_targets.items():
        contributors = [(raw[c.id], c.cpl_mapping[key]) for c in data.cpmks if key in c.cpl_mapping]
        complete = all(score is not None for score, _ in contributors)
        score = sum(s * w for s, w in contributors) / sum(w for _, w in contributors) if complete else None
        cpls.append({"id": key, "score": number(score), "target": number(target),
                     "status": "incomplete" if not complete else "gap" if score < target else "achieved"})
    return {"formula_version": "weighted-course-v1", "scope": "course_only", "cpmks": cpmks, "cpls": cpls}
