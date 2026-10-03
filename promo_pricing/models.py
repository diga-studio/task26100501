"""类型定义：商品、规则与试算结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class DiscountKind(Enum):
    """优惠类型。"""

    FIXED_CENTS = "fixed_cents"
    PERCENT_BPS = "percent_bps"


@dataclass(frozen=True)
class Product:
    """商品：SKU 与美元标价（整数美分）。"""

    sku: str
    price_cents: int


@dataclass(frozen=True)
class Rule:
    """优惠规则。

    - rule_id: 唯一 ID
    - skus: 目标 SKU 集合
    - start_utc / end_utc: 有效期（UTC 秒级时刻，含开始、不含结束）
    - kind: 优惠类型（定额美分 / 比例基点）
    - value: 定额的美分数，或比例的基点数（1 基点 = 0.01%）
    - mutex_group: 可选互斥组名，同组至多选一条
    """

    rule_id: str
    skus: frozenset
    start_utc: int
    end_utc: int
    kind: DiscountKind
    value: int
    mutex_group: Optional[str] = None


@dataclass(frozen=True)
class Quote:
    """单个 SKU 的试算结果：最低成交价（美分）与采用的规则 ID 序列。"""

    sku: str
    final_price_cents: int
    rule_ids: Tuple[str, ...] = field(default_factory=tuple)
