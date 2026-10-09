import unittest
from pathlib import Path

import pandas as pd

from engine import predict

DATA = Path(__file__).resolve().parents[2] / "dataset"


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products, cls.txns = predict.load_data(DATA)
        cls.cutoff = cls.txns[cls.txns.split == "train"].date.max()

    def test_no_future_leakage(self):
        """Forecast must not change if future transactions are removed."""
        past = self.txns[self.txns.date <= self.cutoff]
        a = predict.daily_sales("BEV-001", self.cutoff, self.txns)
        b = predict.daily_sales("BEV-001", self.cutoff, past)
        pd.testing.assert_series_equal(a, b)

    def test_stock_reconciles_except_known_demo_trim(self):
        """Raw reconstructed stock is >= 0 for all SKUs except SNK-001, whose
        final stock the generator trims by hand for the urgent-reorder demo."""
        bad = [sku for sku in self.products.sku
               if predict.stock_as_of(sku, self.cutoff, self.products,
                                      self.txns, clamp=False) < 0]
        self.assertEqual(bad, ["SNK-001"])

    def test_clamped_stock_never_negative(self):
        for sku in self.products.sku:
            self.assertGreaterEqual(
                predict.stock_as_of(sku, self.cutoff, self.products, self.txns), 0)

    def test_cold_start_flagged(self):
        rec = predict.recommend("BEV-007", self.cutoff, self.products, self.txns)
        self.assertEqual(rec.confidence, "low")

    def test_urgent_demo_product(self):
        end = self.txns.date.max()
        rec = predict.recommend("SNK-001", end, self.products, self.txns)
        self.assertTrue(rec.should_reorder)
        self.assertGreater(rec.recommended_qty, 0)

    def test_beats_naive_baseline(self):
        _, scores, _ = predict.backtest(self.products, self.txns)
        self.assertLess(scores["engine"]["WAPE"], scores["naive"]["WAPE"])


if __name__ == "__main__":
    unittest.main()
