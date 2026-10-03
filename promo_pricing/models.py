"""数据模型：商品、规则与快照。金额一律为整数美分，时间为 UTC 秒级时刻。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional, Tuple


class DiscountKind(Enum):
    """优惠类型：定额减美分，或按基点比例优惠当前价格。"""

    FIXED_CENTS = "fixed_cents"
    PERCENT_BPS = "percent_bps"


@dataclass(frozen=True)
class Product:
    sku: str
    price_cents: int


@dataclass(frozen=True)
class Rule:
    """单条优惠规则。

    - rule_id: 唯一 ID
    - skus: 目标 SKU 集合
    - start / end: 有效期，UTC 秒，含开始不含结束
    - kind + value: FIXED_CENTS 时 value 为美分；PERCENT_BPS 时 value 为基点
    - exclusive_group: 可选互斥组，同组至多选一条
    - incompatible_with: 与指定规则两两互斥（声明一侧即可，装载时对称化）
    """

    rule_id: str
    skus: FrozenSet[str]
    start: int
    end: int
    kind: DiscountKind
    value: int
    exclusive_group: Optional[str] = None
    incompatible_with: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class QuoteResult:
    """单个 SKU 的试算结果：最低成交价（美分）与采用的规则 ID 序列。"""

    sku: str
    price_cents: int
    rule_ids: Tuple[str, ...]
