"""试算引擎：装载不可变快照，为一批 SKU 在指定时刻求最低合法成交价。"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .models import DiscountKind, Product, QuoteResult, Rule


def _apply(rule: Rule, price_cents: int) -> int:
    """把单条规则作用于当前价格，返回取整后的新价格。"""
    if rule.kind is DiscountKind.FIXED_CENTS:
        return max(0, price_cents - rule.value)
    discount = (price_cents * rule.value + 5000) // 10000
    return price_cents - discount


class Snapshot:
    """商品与规则的完整快照，装入后保持不变。"""

    def __init__(self, products: Iterable[Product], rules: Iterable[Rule]) -> None:
        self._products = {p.sku: p for p in products}
        rule_list = list(rules)
        ids = [r.rule_id for r in rule_list]
        if len(set(ids)) != len(ids):
            raise ValueError("规则 ID 必须唯一")
        self._rules: Tuple[Rule, ...] = tuple(sorted(rule_list, key=lambda r: r.rule_id))
        # 两两互斥对称化：任一侧声明即双向生效
        incompatible: Dict[str, set] = {r.rule_id: set(r.incompatible_with) for r in rule_list}
        for r in rule_list:
            for other in r.incompatible_with:
                incompatible.setdefault(other, set()).add(r.rule_id)
        self._incompatible = {k: frozenset(v) for k, v in incompatible.items()}

    def quote(self, skus: Iterable[str], at: int) -> Dict[str, QuoteResult]:
        """为一批 SKU 在 UTC 秒级时刻 at 试算，返回 sku -> QuoteResult。"""
        return {sku: self._quote_one(sku, at) for sku in skus}

    def _quote_one(self, sku: str, at: int) -> QuoteResult:
        if sku not in self._products:
            raise KeyError(f"快照中不存在 SKU: {sku}")
        base = self._products[sku].price_cents
        applicable = [
            r for r in self._rules if sku in r.skus and r.start <= at < r.end
        ]
        best_key = None
        best_ids: Tuple[str, ...] = ()
        n = len(applicable)
        for mask in range(0, 1 << n):
            chosen = [applicable[i] for i in range(n) if mask >> i & 1]
            if not self._legal(chosen):
                continue
            price = base
            for r in chosen:  # applicable 已按 ID 升序
                price = _apply(r, price)
            ids = tuple(r.rule_id for r in chosen)
            key = (price, len(chosen), ids)
            if best_key is None or key < best_key:
                best_key = key
                best_ids = ids
        return QuoteResult(sku=sku, price_cents=best_key[0], rule_ids=best_ids)

    def _legal(self, chosen: List[Rule]) -> bool:
        groups = set()
        ids = set()
        for r in chosen:
            if r.exclusive_group is not None:
                if r.exclusive_group in groups:
                    return False
                groups.add(r.exclusive_group)
            ids.add(r.rule_id)
        for r in chosen:
            if self._incompatible.get(r.rule_id, frozenset()) & ids:
                return False
        return True
