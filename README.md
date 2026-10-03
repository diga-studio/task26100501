# task26100501

## promo_pricing：季节商品促销试算库

纯 Python、零第三方依赖的库，由上层直接调用。为一批 SKU 在指定 UTC 时刻求
最低合法成交价及采用的完整规则 ID 序列。

### 概念

- 金额一律为整数美分；时间为 UTC 秒级时刻，有效期含开始、不含结束。
- 优惠两类：`FIXED_CENTS`（定额减美分，最低减到零）、`PERCENT_BPS`
  （按基点比例优惠当前价格，1 基点 = 0.01%，结果四舍五入到美分，半美分向上）。
- 每个商品可选任意合法规则子集（可为空），每条规则至多一次；
  入选规则按 ID 升序依次作用，每步取整结果参与下一步。
- 互斥约束：`exclusive_group` 同组至多一条；`incompatible_with` 声明两两互斥
  （任一侧声明即双向生效），跨组有效。未生效/不适用的规则不阻止其他规则。
- 裁决：先比最低成交价，再比规则条数最少，再比升序 ID 序列字典序最小。
  输入排列顺序不影响结果。

### 用法

```python
from promo_pricing import DiscountKind, Product, Rule, Snapshot

products = [Product("SKU1", 10000)]  # 100 美元
rules = [
    Rule("A40", frozenset({"SKU1"}), 0, 2_000_000_000,
         DiscountKind.PERCENT_BPS, 4000,
         incompatible_with=frozenset({"B30", "C25"})),
    Rule("B30", frozenset({"SKU1"}), 0, 2_000_000_000,
         DiscountKind.FIXED_CENTS, 3000),
    Rule("C25", frozenset({"SKU1"}), 0, 2_000_000_000,
         DiscountKind.FIXED_CENTS, 2500),
]

snap = Snapshot(products, rules)      # 装入后保持不变
out = snap.quote(["SKU1"], at=1_700_000_000)
print(out["SKU1"].price_cents)        # 4500（45 美元）
print(out["SKU1"].rule_ids)           # ('B30', 'C25')
```

### 测试

```bash
python3 -m unittest discover -s tests -v
```
