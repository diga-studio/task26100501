"""试算引擎：装入不可变快照，为一批 SKU 在指定时刻求最低合法成交价。"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, FrozenSet, Iterable, List, Tuple

from .models import DiscountKind, Product, Quote, Rule

_BPS_BASE = 10000


def _apply_rule(price_cents: int, rule: Rule) -> int:
    """把一条规则作用于当前价格，返回取整后的新价格。"""
    if rule.kind is DiscountKind.FIXED_CENTS:
        return max(0, price_cents - rule.value)
    remaining = price_cents * (_BPS_BASE - rule.value)
    return (remaining + _BPS_BASE // 2) // _BPS_BASE


class PromoEngine:
    """促销试算引擎。

    通过 :meth:`load_snapshot` 装入一份完整商品及规则快照，
    装入后快照保持不变；随后可在指定 UTC 秒级时刻为一批 SKU 试算。
    """

    def __init__(self) -> None:
        self._products: Dict[str, Product] = {}
        self._rules: Tuple[Rule, ...] = ()
        self._incompatible: FrozenSet[FrozenSet[str]] = frozenset()

    def load_snapshot(
        self,
        products: Iterable[Product],
        rules: Iterable[Rule],
        incompatible_pairs: Iterable[Tuple[str, str]] = (),
    ) -> None:
        """装入完整快照（商品、规则、两两互斥声明），替换此前内容。"""
        products = list(products)
        rules = list(rules)
        skus = [p.sku for p in products]
        if len(set(skus)) != len(skus):
            raise ValueError("商品 SKU 存在重复")
        rule_ids = [r.rule_id for r in rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("规则 ID 存在重复")
        known = set(rule_ids)
        pairs = set()
        for a, b in incompatible_pairs:
            if a == b:
                raise ValueError(f"互斥声明的两个规则相同: {a}")
            if a not in known or b not in known:
                raise ValueError(f"互斥声明引用了未知规则: {a}, {b}")
            pairs.add(frozenset((a, b)))
        self._products = {p.sku: p for p in products}
        self._rules = tuple(sorted(rules, key=lambda r: r.rule_id))
        self._incompatible = frozenset(pairs)

    def quote(self, skus: Iterable[str], at_utc: int) -> List[Quote]:
        """在指定时刻为一批 SKU 试算，按输入 SKU 顺序返回结果。"""
        return [self._quote_one(sku, at_utc) for sku in skus]

    def _quote_one(self, sku: str, at_utc: int) -> Quote:
        if sku not in self._products:
            raise KeyError(f"未知 SKU: {sku}")
        product = self._products[sku]
        candidates = [
            r
            for r in self._rules
            if sku in r.skus and r.start_utc <= at_utc < r.end_utc
        ]
        best_price = product.price_cents
        best_ids: Tuple[str, ...] = ()
        for size in range(1, len(candidates) + 1):
            for subset in combinations(candidates, size):
                if not self._is_legal(subset):
                    continue
                price = product.price_cents
                for rule in subset:  # candidates 已按 ID 升序
                    price = _apply_rule(price, rule)
                ids = tuple(r.rule_id for r in subset)
                if (price, len(ids), ids) < (best_price, len(best_ids), best_ids):
                    best_price = price
                    best_ids = ids
        return Quote(sku=sku, final_price_cents=best_price, rule_ids=best_ids)

    def _is_legal(self, subset: Tuple[Rule, ...]) -> bool:
        groups = [r.mutex_group for r in subset if r.mutex_group is not None]
        if len(groups) != len(set(groups)):
            return False
        ids = [r.rule_id for r in subset]
        for a, b in combinations(ids, 2):
            if frozenset((a, b)) in self._incompatible:
                return False
        return True
