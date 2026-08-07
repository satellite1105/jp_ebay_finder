# 03. 利益計算・候補判定・ランキング仕様

## 1. 目的

このシステムの中心はAIではなく、再現可能な利益計算である。

LLMには検索語生成、名称正規化、説明文生成などを担当させてもよいが、金額、利益率、採否判定はPythonの決定論的ロジックで処理する。

## 2. 金額計算の原則

- Pythonの `decimal.Decimal` を使う
- DBの金額は原則として最小通貨単位の整数、または `DECIMAL` で保存する
- 円は整数で保存してよい
- USDなどの外貨は `DECIMAL(18, 6)` を推奨する
- 為替、手数料率、税率は計算日時点の値をスナップショットとして保存する
- 計算後の結果だけでなく、使用した前提値も保存する
- `float` を利益計算に使わない

## 3. 入力値

### 3.1 売上側

| 変数 | 内容 |
|---|---|
| `item_price_usd` | 商品価格 |
| `buyer_shipping_usd` | 購入者負担送料 |
| `buyer_tax_usd` | プラットフォームが徴収する税。売上に含めるかは手数料定義に従う |
| `exchange_rate_jpy_per_usd` | 使用為替レート |

### 3.2 原価側

| 変数 | 内容 |
|---|---|
| `source_item_cost_jpy` | 商品仕入原価 |
| `source_domestic_shipping_jpy` | 国内送料の按分 |
| `source_transport_jpy` | 店舗巡回・交通費の按分 |
| `packaging_jpy` | 封筒、箱、緩衝材、ラベル等 |
| `international_shipping_jpy` | 国際送料 |
| `duty_jpy` | 関税見込み |
| `import_processing_jpy` | 通関・DDP・配送事業者処理費 |
| `marketplace_fee_jpy` | eBay等の販売手数料 |
| `international_fee_jpy` | 国際取引手数料 |
| `currency_conversion_jpy` | 通貨換算コスト |
| `promoted_listing_jpy` | 広告費 |
| `payment_fee_jpy` | 別途発生する場合のみ |
| `return_reserve_jpy` | 返品・再送・未着・破損の期待損失 |
| `labor_cost_jpy` | 任意。作業時間を原価として評価する場合 |
| `other_cost_jpy` | その他 |

## 4. 基本計算式

```text
buyer_total_usd
  = item_price_usd
  + buyer_shipping_usd

recognized_revenue_jpy
  = buyer_total_usd
  × exchange_rate_jpy_per_usd

variable_marketplace_fee_jpy
  = fee_base_jpy
  × marketplace_fee_rate

marketplace_fee_jpy
  = variable_marketplace_fee_jpy
  + marketplace_fixed_fee_jpy

promoted_listing_jpy
  = ad_fee_base_jpy
  × promoted_listing_rate

return_reserve_jpy
  = recognized_revenue_jpy
  × return_reserve_rate

total_cost_jpy
  = source_item_cost_jpy
  + source_domestic_shipping_jpy
  + source_transport_jpy
  + packaging_jpy
  + international_shipping_jpy
  + duty_jpy
  + import_processing_jpy
  + marketplace_fee_jpy
  + international_fee_jpy
  + currency_conversion_jpy
  + promoted_listing_jpy
  + payment_fee_jpy
  + return_reserve_jpy
  + labor_cost_jpy
  + other_cost_jpy

net_profit_jpy
  = recognized_revenue_jpy
  - total_cost_jpy

net_margin
  = net_profit_jpy
  / recognized_revenue_jpy

capital_efficiency
  = net_profit_jpy
  / cash_required_before_sale_jpy
```

`fee_base_jpy` はプラットフォーム規約に合わせる。商品代だけと決め打ちせず、購入者送料などを含む場合に対応できる設計にする。

## 5. 返品期待損失

単純に売上へ一定率を掛ける簡易方式と、実績ベース方式の両方を用意する。

### 5.1 MVP方式

```text
return_reserve_jpy = revenue_jpy × return_reserve_rate
```

初期値は設定ファイルで2〜4%程度を指定できるようにし、コードへ固定しない。

### 5.2 実績方式

```text
expected_return_loss
  = return_probability
  × (
      refund_amount
      + outbound_shipping_not_recovered
      + return_shipping_support
      + lost_inventory_cost
      + reshipment_cost
    )
```

販売実績が30件未満の場合は、カテゴリ既定値と実績値を加重平均する。

## 6. 三つの採算シナリオ

候補ごとに必ず3シナリオを計算する。

| シナリオ | 売価 | 為替 | 送料 | 広告 | 返品 | 用途 |
|---|---|---|---|---|---|---|
| Optimistic | 市場中央値以上 | 有利 | 下限 | 低 | 低 | 上振れ確認 |
| Base | 市場中央値 | 現在値 | 標準 | 標準 | 標準 | 通常判断 |
| Conservative | 市場中央値の90〜95% | 不利 | 上限 | 高 | 高 | 仕入れ上限判断 |

仕入れ判定では、BaseだけでなくConservativeも確認する。

### 推奨初期設定

```yaml
scenarios:
  optimistic:
    sale_price_multiplier: "1.05"
    exchange_rate_multiplier: "1.02"
    shipping_multiplier: "0.95"
    ad_rate_multiplier: "0.70"
    return_rate_multiplier: "0.70"
  base:
    sale_price_multiplier: "1.00"
    exchange_rate_multiplier: "1.00"
    shipping_multiplier: "1.00"
    ad_rate_multiplier: "1.00"
    return_rate_multiplier: "1.00"
  conservative:
    sale_price_multiplier: "0.92"
    exchange_rate_multiplier: "0.97"
    shipping_multiplier: "1.10"
    ad_rate_multiplier: "1.30"
    return_rate_multiplier: "1.50"
```

## 7. 損益分岐価格

候補商品ごとに、最低販売価格を計算して表示する。

```text
break_even_revenue_jpy
  = fixed_cost_jpy
  / (1 - total_variable_rate)

break_even_buyer_total_usd
  = break_even_revenue_jpy
  / exchange_rate_jpy_per_usd
```

以下の二つを別々に出す。

- `break_even_price_usd`: 利益0円になる価格
- `target_price_usd`: 目標利益3,000円などを達成する価格

```text
target_revenue_jpy
  = (fixed_cost_jpy + target_profit_jpy)
  / (1 - total_variable_rate)
```

## 8. MVPの採用条件

初期値は以下とするが、DBまたはYAMLで変更可能にする。

```yaml
candidate_rules:
  minimum_base_profit_jpy: 3000
  minimum_base_margin: "0.25"
  minimum_conservative_profit_jpy: 1000
  minimum_sold_90d: 5
  minimum_sell_through_rate: "0.15"
  maximum_packed_weight_g: 1000
  maximum_source_data_age_days: 7
  maximum_market_data_age_days: 90
  minimum_confidence_score: 60
```

## 9. 判定ステータス

優先順位の高いものから適用する。

| ステータス | 条件 |
|---|---|
| `BLOCKED` | 禁止・規制・真贋・危険物などで販売不可 |
| `MISSING_DATA` | 利益計算に必要な主要データがない |
| `STALE_DATA` | 国内価格または市場データが古い |
| `REVIEW_COMPLIANCE` | 人間による規制確認が必要 |
| `LOW_DEMAND` | 販売数またはSell-throughが基準未満 |
| `LOW_PROFIT` | 利益額または利益率が基準未満 |
| `WATCH` | 良いが、仕入れ前に追加確認が必要 |
| `BUY_TEST_1` | 1個だけテスト仕入れ |
| `BUY_TEST_2` | 2個テスト仕入れ可能 |
| `REPLENISH` | 実販売データがあり補充条件を満たす |

### 判定例

```python
if compliance_status == "blocked":
    return "BLOCKED"
if missing_required_fields:
    return "MISSING_DATA"
if source_data_is_stale or market_data_is_stale:
    return "STALE_DATA"
if compliance_status == "review":
    return "REVIEW_COMPLIANCE"
if sold_90d < min_sold or sell_through_rate < min_str:
    return "LOW_DEMAND"
if base_profit < min_profit or base_margin < min_margin:
    return "LOW_PROFIT"
if confidence_score < min_confidence:
    return "WATCH"
if conservative_profit >= min_conservative_profit and cash_required <= test_budget_limit:
    return "BUY_TEST_2"
return "BUY_TEST_1"
```

## 10. 機会スコア

利益額だけで並べると、売れない高額商品が上位になる。以下を0〜100点で評価する。

| 要素 | 配点 | 内容 |
|---|---:|---|
| Base純利益 | 25 | 3,000円から高評価、上限を設定 |
| Base利益率 | 15 | 25%から高評価 |
| 90日販売数 | 15 | 対数変換して一部商品の突出を抑える |
| Sell-through rate | 10 | 需要と競合の均衡 |
| 資金効率 | 10 | 利益÷売れるまでに必要な資金 |
| Conservative耐性 | 10 | 悪条件でも利益が残るか |
| データ信頼度 | 10 | JAN一致、型番一致、件数、鮮度 |
| 継続仕入れ | 5 | 定番・在庫安定性 |
| リスク控除 | -30まで | 規制、真贋、破損、返品、適合性 |

### 正規化例

```python
profit_score = min(max((base_profit_jpy - 1000) / 5000, 0), 1) * 25
margin_score = min(max((base_margin - Decimal("0.10")) / Decimal("0.40"), 0), 1) * 15
sales_score = min(math.log1p(sold_90d) / math.log1p(100), 1) * 15
str_score = min(sell_through_rate / Decimal("0.60"), 1) * 10
capital_score = min(capital_efficiency / Decimal("1.00"), 1) * 10
```

実装では、各スコアの根拠値もDBへ保存する。

## 11. データ信頼度

### 推奨配点

| 条件 | 点数 |
|---|---:|
| JAN完全一致 | +35 |
| メーカー型番完全一致 | +30 |
| ブランド＋型番一致 | +20 |
| タイトル類似度90%以上 | +15 |
| 市場データ10件以上 | +10 |
| 国内価格7日以内 | +5 |
| 重量が実測 | +5 |
| 原産国が実物確認済み | +5 |
| 商品状態不一致 | -25 |
| 内容量・セット数不一致 | -30 |
| 型番曖昧 | -20 |

0〜100へ丸める。

`confidence_score < 60` は自動仕入れ候補にしない。

## 12. セット商品の計算

セット商品は構成品テーブルを作り、合計原価・重量を計算する。

```text
bundle_cost
  = Σ(component_cost × quantity)

bundle_weight
  = Σ(component_weight × quantity)
  + packaging_weight
```

セット内商品のいずれかが規制対象なら、セット全体をブロックまたは要確認にする。

## 13. 実績利益への更新

販売後は予測値だけでなく、注文単位の実績値を保存する。

最低限保存する項目:

- 実売価格
- 実為替
- 実販売手数料
- 実広告費
- 実送料
- 実関税・処理費
- 返金額
- 実梱包費
- 実作業時間
- 最終純利益

予測誤差を以下で計測する。

```text
profit_error_jpy = actual_net_profit_jpy - predicted_base_profit_jpy
profit_error_rate = profit_error_jpy / abs(predicted_base_profit_jpy)
```

誤差が大きい費目を毎月集計し、送料・返品・関税の既定値を更新する。

## 14. 禁止事項

- LLMへ利益計算を委ねない
- 手数料率をコードへ直書きしない
- 古い市場価格を現在値として扱わない
- 商品価格だけを見て利益判定しない
- 「売れた件数不明」を0件または推定値で埋めない
- 原産国不明を日本製として扱わない
- 商品状態やセット数が異なる競合を同一比較しない
