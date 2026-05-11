"""Tests for CostGuard budget management."""


class TestCostGuard:
    """Tests for the cost guard."""

    def test_check_under_budget(self):
        """Test that spending under budget is allowed."""
        from minerva.executor.executor import CostGuard

        guard = CostGuard(monthly_budget=50.0, ledger_path="/tmp/test_cost_ledger.jsonl")
        assert guard.check(10.0) is True
        assert guard.check(30.0) is True  # 40 total, still under 50

    def test_check_exceeded(self):
        """Test that exceeding budget is blocked."""
        from minerva.executor.executor import CostGuard

        guard = CostGuard(monthly_budget=50.0, ledger_path="/tmp/test_cost_ledger.jsonl")
        guard.record(45.0)
        # 45 + 10 = 55 > 50 → blocked
        assert guard.check(10.0) is False

    def test_warn_threshold(self):
        """Test that warning threshold is reported correctly."""
        from minerva.executor.executor import CostGuard

        guard = CostGuard(monthly_budget=50.0, warn_pct=0.80, ledger_path="/tmp/test_cost_warn.jsonl")
        guard.record(42.0)  # 84% used

        status = guard.get_status()
        assert status["current_spend"] == 42.0
        assert status["remaining"] == 8.0
        assert status["pct_used"] == 84.0
