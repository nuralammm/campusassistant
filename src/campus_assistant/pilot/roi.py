"""All periods in months, all money in IDR; blank data means HOLD."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ROIInput:
    baseline_hours_month: Decimal
    new_work_hours_month: Decimal
    review_hours_month: Decimal
    correction_hours_month: Decimal
    value_per_hour: Decimal
    monthly_operating_cost: Decimal
    initial_cost: Decimal
    horizon_months: int

    def __post_init__(self):
        values = (self.baseline_hours_month, self.new_work_hours_month,
                  self.review_hours_month, self.correction_hours_month,
                  self.value_per_hour, self.monthly_operating_cost, self.initial_cost)
        if any(not v.is_finite() or v < 0 for v in values):
            raise ValueError("nonnegative finite inputs required")
        if self.horizon_months <= 0:
            raise ValueError("positive horizon required")


def calculate(data: ROIInput) -> dict:
    saved = (data.baseline_hours_month - data.new_work_hours_month
             - data.review_hours_month - data.correction_hours_month)
    benefit = saved * data.value_per_hour
    net = benefit - data.monthly_operating_cost
    cost = data.initial_cost + data.monthly_operating_cost * data.horizon_months
    total_benefit = benefit * data.horizon_months
    return {
        "net_hours_saved_month": saved,
        "capacity_benefit_month_idr": benefit,
        "net_benefit_month_idr": net,
        "horizon_cost_idr": cost,
        "horizon_roi_pct": ((total_benefit - cost) / cost * 100) if cost else None,
        "payback_months": data.initial_cost / net if net > 0 else None,
        "time_reduction_pct": saved / data.baseline_hours_month * 100
        if data.baseline_hours_month else None,
    }


def release_gate(*, evidence_complete: bool, security_passed: bool,
                 controls_passed: bool, outcome_tests_passed: bool,
                 quality_rate: Decimal | None, time_reduction_pct: Decimal | None,
                 incremental_ai_benefit_idr: Decimal | None,
                 payback_months: Decimal | None,
                 max_payback_months: Decimal = Decimal("12")) -> dict:
    """Hard safety failures cannot be offset by financial scores."""
    if not all((security_passed, controls_passed, outcome_tests_passed)):
        return {"decision": "NO_GO", "reason": "hard_gate_failed"}
    values = (quality_rate, time_reduction_pct, incremental_ai_benefit_idr, payback_months)
    if not evidence_complete or any(v is None for v in values):
        return {"decision": "HOLD", "reason": "missing_evidence"}
    if any(not v.is_finite() for v in values) or not max_payback_months.is_finite():
        return {"decision": "HOLD", "reason": "invalid_metrics"}
    if not Decimal("0") <= quality_rate <= Decimal("1") or payback_months < 0 or max_payback_months <= 0:
        return {"decision": "HOLD", "reason": "invalid_metrics"}
    passed = (quality_rate >= Decimal("0.85") and time_reduction_pct >= Decimal("25")
              and incremental_ai_benefit_idr > 0 and payback_months <= max_payback_months)
    return {"decision": "GO" if passed else "NO_GO",
            "reason": "pilot_targets_met" if passed else "value_gate_failed"}
