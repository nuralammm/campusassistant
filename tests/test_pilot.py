import unittest
from dataclasses import replace
from decimal import Decimal as D
from campus_assistant.pilot.decision import Context, Policy, Status, decide
from campus_assistant.pilot.roi import ROIInput, calculate, release_gate


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(True, "draft_intervention", ("ASM-02",), "v1", "v1")

    def test_valid_draft(self):
        self.assertEqual(decide(self.ctx).status, Status.PROCEED)

    def test_cross_class_denial(self):
        self.assertEqual(decide(replace(self.ctx, authorized=False)).status, Status.BLOCK)

    def test_missing_and_stale_evidence(self):
        for change in ({"missing_required": True}, {"current_version": "v2"}, {"evidence_ids": ()}):
            self.assertEqual(decide(replace(self.ctx, **change)).status, Status.CLARIFY)

    def test_forbidden_grade_write(self):
        self.assertEqual(decide(replace(self.ctx, action="change_grade")).status, Status.BLOCK)

    def test_shadow_cannot_publish_even_with_approval(self):
        self.assertEqual(decide(replace(self.ctx, action="publish_intervention",
                         approval_valid_for_snapshot=True)).status, Status.BLOCK)

    def test_reviewed_publish_requires_snapshot_bound_approval(self):
        ctx = replace(self.ctx, action="publish_intervention", mode="reviewed")
        self.assertEqual(decide(ctx).status, Status.APPROVAL)
        self.assertEqual(decide(replace(ctx, approval_valid_for_snapshot=True)).status, Status.PROCEED)
        self.assertEqual(decide(replace(ctx, approval_valid_for_snapshot=True,
                         current_version="v2")).status, Status.CLARIFY)

    def test_limits_and_kill_switch(self):
        for change in ({"kill_switch": True}, {"steps_used": 4}, {"elapsed_seconds": 60},
                       {"spent_idr": D("4999"), "next_cost_upper_idr": D("2")}):
            self.assertEqual(decide(replace(self.ctx, **change)).status, Status.STOP)

    def test_invalid_input_fails_closed(self):
        for change in ({"spent_idr": D("NaN")}, {"next_cost_upper_idr": D("-1")},
                       {"mode": "autonomous"}, {"steps_used": -1}):
            self.assertEqual(decide(replace(self.ctx, **change)).status, Status.BLOCK)
        with self.assertRaises(ValueError):
            Policy(max_steps=0)


class ROITests(unittest.TestCase):
    def test_horizon_cost_includes_investment(self):
        data = ROIInput(D("50"), D("12"), D("6"), D("2"), D("100000"),
                        D("1500000"), D("12000000"), 12)
        result = calculate(data)
        self.assertEqual(result["net_hours_saved_month"], 30)
        self.assertEqual(result["payback_months"], 8)
        self.assertEqual(result["horizon_roi_pct"], 20)

    def test_negative_savings_no_payback(self):
        data = ROIInput(D("1"), D("2"), D("1"), D("0"), D("100"), D("50"), D("1000"), 12)
        self.assertIsNone(calculate(data)["payback_months"])

    def test_invalid_financial_values(self):
        with self.assertRaises(ValueError):
            ROIInput(D("NaN"), D("0"), D("0"), D("0"), D("1"), D("1"), D("1"), 12)

    def test_release_gate_safety_overrides_roi(self):
        args = dict(evidence_complete=True, security_passed=True, controls_passed=True,
                    outcome_tests_passed=True, quality_rate=D("0.9"), time_reduction_pct=D("30"),
                    incremental_ai_benefit_idr=D("100"), payback_months=D("8"))
        self.assertEqual(release_gate(**args)["decision"], "GO")
        self.assertEqual(release_gate(**(args | {"security_passed": False}))["decision"], "NO_GO")
        self.assertEqual(release_gate(**(args | {"quality_rate": None}))["decision"], "HOLD")
        self.assertEqual(release_gate(**(args | {"incremental_ai_benefit_idr": D("-1")}))["decision"], "NO_GO")


if __name__ == "__main__":
    unittest.main()
