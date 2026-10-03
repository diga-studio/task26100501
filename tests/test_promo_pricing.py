"""promo_pricing 自动化测试。"""

import unittest

from promo_pricing import DiscountKind, PromoEngine, Product, Rule

NOW = 1_700_000_000
DAY = 86_400


def pct(rule_id, skus, bps, group=None, start=NOW - DAY, end=NOW + DAY):
    return Rule(rule_id, frozenset(skus), start, end,
                DiscountKind.PERCENT_BPS, bps, group)


def fix(rule_id, skus, cents, group=None, start=NOW - DAY, end=NOW + DAY):
    return Rule(rule_id, frozenset(skus), start, end,
                DiscountKind.FIXED_CENTS, cents, group)


class TestRequiredScenarios(unittest.TestCase):
    def test_clearance_combo_beats_single_rule(self):
        """100 美元：-40% 与 -$30/-$25 互斥，后两条叠加得 45 美元。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("SKU-1", 100_00)],
            rules=[
                pct("R-PCT40", {"SKU-1"}, 4000),
                fix("R-LESS30", {"SKU-1"}, 30_00),
                fix("R-LESS25", {"SKU-1"}, 25_00),
            ],
            incompatible_pairs=[("R-PCT40", "R-LESS30"),
                                ("R-PCT40", "R-LESS25")],
        )
        (q,) = eng.quote(["SKU-1"], NOW)
        self.assertEqual(q.final_price_cents, 45_00)
        self.assertEqual(q.rule_ids, ("R-LESS25", "R-LESS30"))

    def test_tie_prefers_fewer_rules_then_lexicographic(self):
        """5 美分：10% 再减 1 美分 == 只减 1 美分，必须只选定额规则。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("SKU-2", 5)],
            rules=[
                pct("R-PCT10", {"SKU-2"}, 1000),
                fix("R-LESS1", {"SKU-2"}, 1),
            ],
        )
        (q,) = eng.quote(["SKU-2"], NOW)
        self.assertEqual(q.final_price_cents, 4)
        self.assertEqual(q.rule_ids, ("R-LESS1",))

    def test_same_count_lexicographic_tiebreak(self):
        """规则数量相同且同价时，选升序 ID 序列字典序最小者。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("SKU-3", 5)],
            rules=[
                fix("R-B", {"SKU-3"}, 1, group="g"),
                fix("R-A", {"SKU-3"}, 1, group="g"),
            ],
        )
        (q,) = eng.quote(["SKU-3"], NOW)
        self.assertEqual(q.final_price_cents, 4)
        self.assertEqual(q.rule_ids, ("R-A",))


class TestValidityWindow(unittest.TestCase):
    def test_start_inclusive_end_exclusive(self):
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 1000)],
            rules=[fix("R", {"S"}, 100, start=NOW, end=NOW + DAY)],
        )
        self.assertEqual(eng.quote(["S"], NOW - 1)[0].final_price_cents, 1000)
        self.assertEqual(eng.quote(["S"], NOW)[0].final_price_cents, 900)
        self.assertEqual(
            eng.quote(["S"], NOW + DAY - 1)[0].final_price_cents, 900)
        self.assertEqual(eng.quote(["S"], NOW + DAY)[0].final_price_cents, 1000)

    def test_inapplicable_rules_do_not_block_others(self):
        """过期/不命中商品的规则不参与求解，也不阻止其他规则。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 1000)],
            rules=[
                fix("EXPIRED", {"S"}, 900, start=NOW - 2 * DAY, end=NOW - DAY),
                fix("OTHER-SKU", {"X"}, 900),
                fix("LIVE", {"S"}, 100),
            ],
            incompatible_pairs=[("EXPIRED", "LIVE"), ("OTHER-SKU", "LIVE")],
        )
        (q,) = eng.quote(["S"], NOW)
        self.assertEqual((q.final_price_cents, q.rule_ids), (900, ("LIVE",)))


class TestMutex(unittest.TestCase):
    def test_mutex_group_allows_at_most_one(self):
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 1000)],
            rules=[
                fix("G1", {"S"}, 100, group="g"),
                fix("G2", {"S"}, 200, group="g"),
            ],
        )
        (q,) = eng.quote(["S"], NOW)
        self.assertEqual((q.final_price_cents, q.rule_ids), (800, ("G2",)))

    def test_pairwise_incompatible_across_groups(self):
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 1000)],
            rules=[
                fix("A", {"S"}, 600, group="g1"),
                fix("B", {"S"}, 500, group="g2"),
                fix("C", {"S"}, 100),
            ],
            incompatible_pairs=[("A", "B")],
        )
        (q,) = eng.quote(["S"], NOW)
        # A+B 互斥；最优为 A+C=300
        self.assertEqual((q.final_price_cents, q.rule_ids), (300, ("A", "C")))


class TestRoundingAndArithmetic(unittest.TestCase):
    def test_half_cent_rounds_up(self):
        """剩余价格恰好半美分时向上取整：5 * 90% = 4.5 -> 5。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 5)],
            rules=[pct("P", {"S"}, 1000)],
        )
        self.assertEqual(eng.quote(["S"], NOW)[0].final_price_cents, 5)

    def test_stepwise_rounding_feeds_next_step(self):
        """每一步取整结果参与下一步：101 -> 91 -> 82，而非一次性 19%。"""
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 101)],
            rules=[pct("P1", {"S"}, 1000), pct("P2", {"S"}, 1000)],
        )
        (q,) = eng.quote(["S"], NOW)
        self.assertEqual(q.final_price_cents, 82)
        self.assertEqual(q.rule_ids, ("P1", "P2"))

    def test_fixed_discount_floors_at_zero(self):
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("S", 300)],
            rules=[fix("BIG", {"S"}, 999)],
        )
        (q,) = eng.quote(["S"], NOW)
        self.assertEqual((q.final_price_cents, q.rule_ids), (0, ("BIG",)))

    def test_no_discount_is_allowed(self):
        eng = PromoEngine()
        eng.load_snapshot(products=[Product("S", 300)], rules=[])
        (q,) = eng.quote(["S"], NOW)
        self.assertEqual((q.final_price_cents, q.rule_ids), (300, ()))


class TestSnapshotAndOrdering(unittest.TestCase):
    def test_input_order_does_not_affect_result(self):
        rules = [
            pct("R-PCT40", {"S"}, 4000),
            fix("R-LESS30", {"S"}, 30_00),
            fix("R-LESS25", {"S"}, 25_00),
        ]
        pairs = [("R-PCT40", "R-LESS30"), ("R-PCT40", "R-LESS25")]
        results = set()
        for order in ([0, 1, 2], [2, 1, 0], [1, 2, 0]):
            eng = PromoEngine()
            eng.load_snapshot(
                products=[Product("S", 100_00)],
                rules=[rules[i] for i in order],
                incompatible_pairs=list(reversed(pairs)),
            )
            (q,) = eng.quote(["S"], NOW)
            results.add((q.final_price_cents, q.rule_ids))
        self.assertEqual(results, {(45_00, ("R-LESS25", "R-LESS30"))})

    def test_snapshot_is_immutable_after_load(self):
        eng = PromoEngine()
        products = [Product("S", 1000)]
        rules = [fix("R", {"S"}, 100)]
        eng.load_snapshot(products=products, rules=rules)
        products.append(Product("T", 1))
        rules.append(fix("R2", {"S"}, 900))
        with self.assertRaises(KeyError):
            eng.quote(["T"], NOW)
        self.assertEqual(eng.quote(["S"], NOW)[0].final_price_cents, 900)

    def test_reload_replaces_previous_snapshot(self):
        eng = PromoEngine()
        eng.load_snapshot(products=[Product("S", 1000)],
                          rules=[fix("R", {"S"}, 100)])
        eng.load_snapshot(products=[Product("S", 1000)], rules=[])
        self.assertEqual(eng.quote(["S"], NOW)[0].final_price_cents, 1000)

    def test_batch_quote_preserves_input_order_and_independence(self):
        eng = PromoEngine()
        eng.load_snapshot(
            products=[Product("A", 1000), Product("B", 500)],
            rules=[fix("R", {"A", "B"}, 100)],
        )
        quotes = eng.quote(["B", "A"], NOW)
        self.assertEqual([q.sku for q in quotes], ["B", "A"])
        self.assertEqual([q.final_price_cents for q in quotes], [400, 900])


class TestValidation(unittest.TestCase):
    def test_unknown_sku_raises(self):
        eng = PromoEngine()
        eng.load_snapshot(products=[Product("S", 100)], rules=[])
        with self.assertRaises(KeyError):
            eng.quote(["NOPE"], NOW)

    def test_duplicate_rule_id_rejected(self):
        eng = PromoEngine()
        with self.assertRaises(ValueError):
            eng.load_snapshot(
                products=[Product("S", 100)],
                rules=[fix("R", {"S"}, 1), pct("R", {"S"}, 100)],
            )

    def test_incompatible_pair_must_reference_known_rules(self):
        eng = PromoEngine()
        with self.assertRaises(ValueError):
            eng.load_snapshot(
                products=[Product("S", 100)],
                rules=[fix("R", {"S"}, 1)],
                incompatible_pairs=[("R", "GHOST")],
            )


if __name__ == "__main__":
    unittest.main()
