"""promo_pricing 引擎的自动化测试（stdlib unittest，无第三方依赖）。"""

import unittest

from promo_pricing import DiscountKind, Product, Rule, Snapshot

NOW = 1_700_000_000  # 任意的 UTC 秒级时刻


def pct(rule_id, skus, value_bps, **kw):
    return Rule(rule_id, frozenset(skus), 0, 2_000_000_000,
                DiscountKind.PERCENT_BPS, value_bps, **kw)


def fixed(rule_id, skus, cents, **kw):
    return Rule(rule_id, frozenset(skus), 0, 2_000_000_000,
                DiscountKind.FIXED_CENTS, cents, **kw)


class ClearanceScenarioTest(unittest.TestCase):
    """场景一：100 美元商品，40% 规则与两定额规则互斥，后两条可叠加。"""

    def _rules(self):
        return [
            pct("A40", {"SKU1"}, 4000, incompatible_with=frozenset({"B30", "C25"})),
            fixed("B30", {"SKU1"}, 3000),
            fixed("C25", {"SKU1"}, 2500),
        ]

    def test_best_is_fixed_pair_at_45(self):
        snap = Snapshot([Product("SKU1", 10000)], self._rules())
        result = snap.quote(["SKU1"], NOW)["SKU1"]
        self.assertEqual(result.price_cents, 4500)
        self.assertEqual(result.rule_ids, ("B30", "C25"))

    def test_input_order_does_not_matter(self):
        rules = self._rules()
        for perm in (rules, rules[::-1], [rules[1], rules[2], rules[0]]):
            snap = Snapshot([Product("SKU1", 10000)], perm)
            result = snap.quote(["SKU1"], NOW)["SKU1"]
            self.assertEqual(result.price_cents, 4500)
            self.assertEqual(result.rule_ids, ("B30", "C25"))


class NickelScenarioTest(unittest.TestCase):
    """场景二：5 美分商品，定额规则与比例规则组合打平时的裁决。"""

    def _rules(self):
        return [
            fixed("F1", {"SKU2"}, 1, incompatible_with=frozenset({"F2"})),
            fixed("F2", {"SKU2"}, 1),
            pct("P10", {"SKU2"}, 1000),
        ]

    def test_only_fixed_rule_chosen(self):
        # F1 先作用 5->4，P10 对 4 美分优惠 0.4 美分四舍五入为 0，
        # {F1, P10} 与 {F1} 同为 4 美分，按条数最少只选 F1；
        # {F2} 与 {F1} 同价同条数，按 ID 序列字典序选 F1。
        snap = Snapshot([Product("SKU2", 5)], self._rules())
        result = snap.quote(["SKU2"], NOW)["SKU2"]
        self.assertEqual(result.price_cents, 4)
        self.assertEqual(result.rule_ids, ("F1",))


class EngineBehaviorTest(unittest.TestCase):
    def test_validity_window_boundaries(self):
        rule = Rule("R", frozenset({"S"}), 100, 200,
                    DiscountKind.FIXED_CENTS, 500)
        snap = Snapshot([Product("S", 1000)], [rule])
        self.assertEqual(snap.quote(["S"], 99)["S"].price_cents, 1000)
        self.assertEqual(snap.quote(["S"], 100)["S"].price_cents, 500)
        self.assertEqual(snap.quote(["S"], 199)["S"].price_cents, 500)
        self.assertEqual(snap.quote(["S"], 200)["S"].price_cents, 1000)

    def test_sku_targeting(self):
        snap = Snapshot([Product("S", 1000), Product("T", 1000)],
                        [fixed("R", {"S"}, 100)])
        out = snap.quote(["S", "T"], NOW)
        self.assertEqual(out["S"].price_cents, 900)
        self.assertEqual(out["T"].price_cents, 1000)
        self.assertEqual(out["T"].rule_ids, ())

    def test_exclusive_group_allows_only_one(self):
        rules = [
            fixed("G1", {"S"}, 300, exclusive_group="g"),
            fixed("G2", {"S"}, 400, exclusive_group="g"),
        ]
        snap = Snapshot([Product("S", 1000)], rules)
        result = snap.quote(["S"], NOW)["S"]
        self.assertEqual(result.price_cents, 600)
        self.assertEqual(result.rule_ids, ("G2",))

    def test_fixed_discount_floors_at_zero(self):
        snap = Snapshot([Product("S", 500)], [fixed("R", {"S"}, 600)])
        self.assertEqual(snap.quote(["S"], NOW)["S"].price_cents, 0)

    def test_percent_rounds_half_cent_up(self):
        # 25% of 10 = 2.5 -> 3，成交价 7
        snap = Snapshot([Product("S", 10)], [pct("R", {"S"}, 2500)])
        self.assertEqual(snap.quote(["S"], NOW)["S"].price_cents, 7)

    def test_sequential_rounding_per_step(self):
        # 10% of 5 = 0.5 -> 1，5-1=4；再 10% of 4 = 0.4 -> 0，结果 4
        # {P1} 与 {P1, P2} 同为 4 美分，按条数最少裁决为 {P1}
        rules = [pct("P1", {"S"}, 1000), pct("P2", {"S"}, 1000)]
        snap = Snapshot([Product("S", 5)], rules)
        result = snap.quote(["S"], NOW)["S"]
        self.assertEqual(result.price_cents, 4)
        self.assertEqual(result.rule_ids, ("P1",))

    def test_pairwise_incompatible_symmetric(self):
        # 只在 B 侧声明互斥，A 侧同样受约束
        rules = [
            fixed("A", {"S"}, 300),
            fixed("B", {"S"}, 400, incompatible_with=frozenset({"A"})),
        ]
        snap = Snapshot([Product("S", 1000)], rules)
        result = snap.quote(["S"], NOW)["S"]
        self.assertEqual(result.price_cents, 600)
        self.assertEqual(result.rule_ids, ("B",))

    def test_inactive_rule_does_not_block(self):
        # 已过期的互斥声明不影响其他规则
        rules = [
            Rule("OLD", frozenset({"S"}), 0, 100,
                 DiscountKind.FIXED_CENTS, 900,
                 incompatible_with=frozenset({"NEW"})),
            fixed("NEW", {"S"}, 500),
        ]
        snap = Snapshot([Product("S", 1000)], rules)
        result = snap.quote(["S"], NOW)["S"]
        self.assertEqual(result.price_cents, 500)
        self.assertEqual(result.rule_ids, ("NEW",))

    def test_unknown_sku_raises(self):
        snap = Snapshot([Product("S", 1000)], [])
        with self.assertRaises(KeyError):
            snap.quote(["MISSING"], NOW)

    def test_duplicate_rule_id_rejected(self):
        rules = [fixed("R", {"S"}, 1), fixed("R", {"S"}, 2)]
        with self.assertRaises(ValueError):
            Snapshot([Product("S", 1000)], rules)

    def test_batch_quote(self):
        snap = Snapshot([Product("A", 100), Product("B", 200)],
                        [fixed("R", {"A", "B"}, 50)])
        out = snap.quote(["B", "A"], NOW)
        self.assertEqual(out["A"].price_cents, 50)
        self.assertEqual(out["B"].price_cents, 150)


if __name__ == "__main__":
    unittest.main()
