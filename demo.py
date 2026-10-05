import json
from decimal import Decimal as D
from campus_assistant.pilot.decision import Context, decide
from campus_assistant.pilot.roi import ROIInput, calculate, release_gate

context = Context(True, "draft_intervention", ("ASM-02",), "synthetic-v1", "synthetic-v1")
result = decide(context)
roi = calculate(ROIInput(D("50"), D("12"), D("6"), D("2"), D("100000"), D("1500000"), D("12000000"), 12))
gate = release_gate(evidence_complete=False, security_passed=True, controls_passed=True,
                    outcome_tests_passed=True, quality_rate=None, time_reduction_pct=None,
                    incremental_ai_benefit_idr=None, payback_months=None)
print(json.dumps({"synthetic_example": True, "jev": {"status": result.status.value, "reason": result.reason},
                  "roi_example_only": roi, "release_actual": gate}, default=str, indent=2))
