#!/usr/bin/env python3
"""ledger.py 离线单元测试：结算判定、日期回退、校验、校准汇总。不访问网络。

运行：python3 tests/test_ledger.py -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ledger  # noqa: E402


def make_closes(pairs: list[tuple[str, float]]) -> dict[str, float]:
    return dict(pairs)


class SettlementMathTest(unittest.TestCase):
    def setUp(self):
        self.closes = make_closes([
            ("2026-09-01", 100.0), ("2026-09-02", 101.0), ("2026-09-03", 102.0),
            ("2026-09-04", 103.0), ("2026-09-07", 104.0), ("2026-09-08", 105.0),
        ])

    def base_pred(self, **kw):
        pred = {
            "id": "t", "asset": {"symbol": "600519", "market": "cn", "name": ""},
            "direction": "long", "confidence": 0.6, "as_of": "2026-09-01",
            "horizon_end": "2026-09-08", "deadband": 0.005,
            "rationale": "test", "invalidate_if": "", "source": "", "status": "open",
        }
        pred.update(kw)
        return pred

    def settle_math(self, pred, closes):
        """绕过网络抓取，把 closes 注入后跑与 settle_one 相同的判定。"""
        base_day, base = ledger.close_on_or_after(closes, pred["as_of"])
        end_day, end = ledger.close_on_or_before(closes, pred["horizon_end"])
        ret = end / base - 1.0
        band = pred.get("deadband", 0.005)
        if pred["direction"] == "long":
            outcome = "hit" if ret > band else "miss"
        elif pred["direction"] == "short":
            outcome = "hit" if ret < -band else "miss"
        else:
            outcome = "hit" if abs(ret) <= band else "miss"
        return ret, outcome

    def test_long_hit_above_deadband(self):
        ret, outcome = self.settle_math(self.base_pred(), self.closes)
        self.assertAlmostEqual(ret, 0.05)
        self.assertEqual(outcome, "hit")

    def test_long_miss_inside_deadband(self):
        closes = make_closes([("2026-09-01", 100.0), ("2026-09-02", 100.3)])
        _, outcome = self.settle_math(self.base_pred(horizon_end="2026-09-02"), closes)
        self.assertEqual(outcome, "miss")  # +0.3% 在 ±0.5% 死区内

    def test_short_hit_on_decline(self):
        closes = make_closes([("2026-09-01", 100.0), ("2026-09-02", 96.0)])
        _, outcome = self.settle_math(self.base_pred(direction="short",
                                                     horizon_end="2026-09-02"), closes)
        self.assertEqual(outcome, "hit")

    def test_short_miss_on_rise(self):
        ret, outcome = self.settle_math(self.base_pred(direction="short"), self.closes)
        self.assertEqual(outcome, "miss")
        self.assertGreater(ret, 0)

    def test_neutral_hit_inside_band(self):
        closes = make_closes([("2026-09-01", 100.0), ("2026-09-02", 100.2)])
        _, outcome = self.settle_math(self.base_pred(direction="neutral",
                                                     horizon_end="2026-09-02"), closes)
        self.assertEqual(outcome, "hit")

    def test_neutral_miss_outside_band(self):
        _, outcome = self.settle_math(self.base_pred(direction="neutral"), self.closes)
        self.assertEqual(outcome, "miss")

    def test_baseline_rolls_forward_to_next_trading_day(self):
        day, _ = ledger.close_on_or_after(self.closes, "2026-08-30")  # 周日
        self.assertEqual(day, "2026-09-01")

    def test_final_rolls_back_to_prev_trading_day(self):
        day, _ = ledger.close_on_or_before(self.closes, "2026-09-06")  # 周日
        self.assertEqual(day, "2026-09-04")

    def test_no_data_after_asof_raises(self):
        with self.assertRaises(RuntimeError):
            ledger.close_on_or_after(self.closes, "2026-10-01")

    def test_no_data_before_horizon_raises(self):
        with self.assertRaises(RuntimeError):
            ledger.close_on_or_before(self.closes, "2026-08-01")


class ValidateTest(unittest.TestCase):
    def base(self, **kw):
        pred = {
            "id": "t", "asset": {"symbol": "600519", "market": "cn", "name": ""},
            "direction": "long", "confidence": 0.6, "as_of": "2026-09-01",
            "horizon_end": "2026-10-01", "rationale": "有理由",
            "invalidate_if": "", "source": "", "status": "open",
        }
        pred.update(kw)
        return pred

    def test_valid_passes(self):
        ledger.validate(self.base())

    def test_empty_rationale_rejected(self):
        with self.assertRaises(ValueError):
            ledger.validate(self.base(rationale="  "))

    def test_horizon_must_be_after_asof(self):
        with self.assertRaises(ValueError):
            ledger.validate(self.base(horizon_end="2026-09-01"))

    def test_confidence_bounds(self):
        with self.assertRaises(ValueError):
            ledger.validate(self.base(confidence=0))
        with self.assertRaises(ValueError):
            ledger.validate(self.base(confidence=1.5))

    def test_cn_symbol_must_be_digits(self):
        with self.assertRaises(ValueError):
            ledger.validate(self.base(asset={"symbol": "AAPL", "market": "cn", "name": ""}))

    def test_bad_direction_rejected(self):
        with self.assertRaises(ValueError):
            ledger.validate(self.base(direction="up"))


class GtimgCodeTest(unittest.TestCase):
    def test_cn_prefixes(self):
        self.assertEqual(ledger.gtimg_code("600519", "cn"), "sh600519")
        self.assertEqual(ledger.gtimg_code("000001", "cn"), "sz000001")
        self.assertEqual(ledger.gtimg_code("300750", "cn"), "sz300750")

    def test_hk_pads_to_five(self):
        self.assertEqual(ledger.gtimg_code("700", "hk"), "hk00700")
        self.assertEqual(ledger.gtimg_code("9988", "hk"), "hk09988")


class ReportTest(unittest.TestCase):
    def test_report_with_data_and_calibration(self):
        settlements = [
            {"id": "a", "return": 0.05, "direction": "long", "confidence": 0.6, "outcome": "hit"},
            {"id": "b", "return": -0.02, "direction": "short", "confidence": 0.6, "outcome": "miss"},
            {"id": "c", "return": 0.10, "direction": "long", "confidence": 0.8, "outcome": "hit"},
            {"id": "d", "return": 0.0, "direction": "neutral", "confidence": 0.5, "outcome": "void"},
        ]
        with tempfile.TemporaryDirectory() as td:
            old_dir, old_stats = ledger.SETTLE_DIR, ledger.STATS_FILE
            ledger.SETTLE_DIR = Path(td)
            for s in settlements:
                (Path(td) / f"{s['id']}.json").write_text(
                    json.dumps(s), encoding="utf-8")
            try:
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ledger.cmd_report(type("A", (), {"write": False})())
            finally:
                ledger.SETTLE_DIR, ledger.STATS_FILE = old_dir, old_stats
            out = buf.getvalue()
        self.assertIn("胜率 **67%**", out)          # 2/3 计分，void 不计入
        self.assertIn("| 0.6 | 2 | 50% |", out)      # 校准分桶
        self.assertIn("| 0.8 | 1 | 100% |", out)
        self.assertIn("+4.33%", out)                  # (0.05-0.02+0.10)/3 均值

    def test_report_empty_is_honest(self):
        with tempfile.TemporaryDirectory() as td:
            old_dir, old_stats = ledger.SETTLE_DIR, ledger.STATS_FILE
            ledger.SETTLE_DIR = Path(td) / "nonexistent"
            try:
                import io, contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ledger.cmd_report(type("A", (), {"write": False})())
            finally:
                ledger.SETTLE_DIR, ledger.STATS_FILE = old_dir, old_stats
            out = buf.getvalue()
        self.assertIn("暂无已结算预测", out)
        self.assertIn("不接受任何形式的回填", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
