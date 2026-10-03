# task26100501 — 季节商品促销试算库

纯 Python 库（仅标准库，Python 3.8+），由上层直接调用。
为一批 SKU 在指定时刻求**最低合法成交价**及采用的完整规则 ID 序列。

## 概念

- **金额**：一律整数美分；**时间**：UTC 秒级时刻，有效期含开始、不含结束。
- **规则**：唯一 ID、目标 SKU 集合、有效期，优惠为定额减美分（最低减到零）
  或按比例基点优惠（1 基点 = 0.01%，作用于当前剩余价格，四舍五入到美分，
  恰好半美分向上取整）。
- **组合**：每个商品可选任意合法规则子集（含空集），每条规则至多一次，
  入选规则按 ID 升序依次作用于当前价格，每步取整结果参与下一步。
- **互斥**：规则可属于一个互斥组（同组至多选一条）；也可声明任意两条规则
  两两互斥（跨组有效）。未生效或不适用的规则不阻止其他规则。
- **裁决**：先比最低成交价；同价比规则条数最少；再同则比升序 ID 序列字典序最小。
  输入排列顺序不影响结果；各商品独立求解。

## 用法

```python
from promo_pricing import DiscountKind, PromoEngine, Product, Rule

engine = PromoEngine()
engine.load_snapshot(
    products=[Product("SKU-1", 100_00)],  # 100 美元
    rules=[
        Rule("R-PCT40",  frozenset({"SKU-1"}), start_utc, end_utc,
             DiscountKind.PERCENT_BPS, 4000),          # 减价 40%
        Rule("R-LESS30", frozenset({"SKU-1"}), start_utc, end_utc,
             DiscountKind.FIXED_CENTS, 30_00),         # 减 30 美元
        Rule("R-LESS25", frozenset({"SKU-1"}), start_utc, end_utc,
             DiscountKind.FIXED_CENTS, 25_00),         # 减 25 美元
    ],
    incompatible_pairs=[("R-PCT40", "R-LESS30"), ("R-PCT40", "R-LESS25")],
)

quotes = engine.quote(["SKU-1"], at_utc=now_utc)
# quotes[0].final_price_cents == 4500
# quotes[0].rule_ids == ("R-LESS25", "R-LESS30")
```

- `load_snapshot(products, rules, incompatible_pairs=())`：装入完整快照，
  替换此前内容；装入后快照保持不变，重复装入以新快照为准。
- `quote(skus, at_utc)`：按输入 SKU 顺序返回 `Quote` 列表，
  每个 `Quote` 含 `sku`、`final_price_cents`、`rule_ids`（升序元组）。
- 未知 SKU 抛 `KeyError`；重复 SKU/规则 ID、互斥声明引用未知规则抛 `ValueError`。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 结构

- `promo_pricing/models.py` — `Product` / `Rule` / `Quote` / `DiscountKind` 类型定义
- `promo_pricing/engine.py` — `PromoEngine`：快照装入与子集枚举求解
- `tests/test_promo_pricing.py` — 18 个用例，覆盖指定场景、有效期边界、
  互斥组与两两互斥、取整与逐步计算、输入顺序无关性、快照不可变与参数校验
