# 実運用前検証レポート(Phase 5: Operational Validation & Decision Trust)

作成日: 2026-08-09
対象: `jp_ebay_finder` MVP(T01〜T41完了、reviewer 0.97)
目的: 現在の利益計算・ランキング・BUY判定を、実際の仕入判断に人間が使ってよい信頼度があるかを検証する。

このレポートはコードとconfigの一次情報(file:line引用)、およびeBay公式・日本郵便公式等の一次情報調査に基づく。**data/samples/配下はテスト用サンプルであり、実市場での精度実証としては扱っていない**(Phase 5D参照)。

---

## 1. 利益計算式(Optimistic / Base / Conservative)

実装: `src/opportunity_finder/domain/profit.py` `calculate_scenario()`(全体でDecimal演算のみ、floatなし)。

シナリオはconfig `config/settings.example.yaml` の `scenario_multipliers`(optimistic/base/conservative、各シナリオごとに `sale_price_multiplier` / `exchange_rate_multiplier` / `shipping_multiplier` / `ad_rate_multiplier` / `return_rate_multiplier`)を、共通のベース値に掛け合わせて算出する(profit.py:20-27)。

計算順序:
1. `buyer_total_usd = item_price_usd×sale_price_multiplier + buyer_shipping_usd×shipping_multiplier`(profit.py:20-29)
2. `recognized_revenue_jpy = buyer_total_usd × exchange_rate_jpy_per_usd`(profit.py:22-30、為替もシナリオ倍率で変動)
3. 手数料算定基礎(`fee_base_jpy`)は `fee_base_is_item_price_only` フラグで「商品価格のみ」か「商品価格+送料」かを切替(profit.py:32-35)
4. `marketplace_fee_jpy = fee_base_jpy × marketplace_fee_rate + marketplace_fixed_fee_jpy`(profit.py:37-38)
5. `promoted_listing_jpy = fee_base_jpy × (ad_rate × ad_rate_multiplier)`(profit.py:26,39)
6. `return_reserve_jpy = recognized_revenue_jpy × (return_reserve_rate × return_rate_multiplier)`(profit.py:27,40)
7. `international_fee_jpy = international_fee_rate × recognized_revenue_jpy`(profit.py:41、シナリオ倍率の対象外)
8. 固定費(`fixed_cost_jpy`)= 仕入原価+国内送料+輸送費+梱包費+国際送料+関税+輸入通関費+為替手数料+決済手数料+人件費+その他(profit.py:43-55)
9. `net_profit_jpy = recognized_revenue_jpy - (fixed_cost_jpy + variable_cost_jpy)`(profit.py:59-60)
10. 損益分岐点 `break_even_buyer_total_usd` と目標価格 `target_price_usd` を寄与利益率から逆算(profit.py:72-77)

**確認事項**: 計算式自体に浮動小数点は使われておらず(`Decimal`のみ)、CLAUDE.mdの絶対条件を満たす。国際手数料(`international_fee_jpy`)だけがシナリオ乗数の対象外(常に一定率)である点は仕様上の意図か未確認 — 楽観/悲観シナリオでも国際手数料率自体は変動しないという設計判断(profit.py:41)。

## 2. Opportunity Score(0〜100)

実装: `src/opportunity_finder/domain/scoring.py` `calculate_opportunity_score()`。

| 要素 | 満点 | 計算方法 |
|---|---|---|
| base_profit | 25点 | `(base_profit_jpy - 1000) / 5000` を0〜1にクランプ(scoring.py:26) |
| base_margin | 15点 | `(base_margin - 0.10) / 0.40` を0〜1にクランプ(scoring.py:27) |
| sold_90d | 15点 | `ln(sold+1) / ln(101)` の対数スケール(scoring.py:29-31) |
| sell_through_rate | 10点 | `rate / 0.60` クランプ(scoring.py:33) |
| capital_efficiency | 10点 | `efficiency / 1.0` クランプ(scoring.py:34) |
| conservative_profit | 10点 | `profit / 3000` クランプ(scoring.py:35) |
| data_confidence | 10点 | `confidence / 100` クランプ(scoring.py:36) |
| replenishable | 5点 | 再仕入可能フラグなら定額付与(scoring.py:37) |
| risk_deduction | -最大30点 | 重複しないrisk_flag数×10点減点、上限30(scoring.py:39-40) |

すべて**コードにハードコードされた**閾値・重み(1000円、5000円、0.10、0.40、0.60、3000円、100、5点、10点等)であり、configファイルでは変更できない。

## 3. Decision判定ロジック(優先順位固定)

実装: `src/opportunity_finder/domain/decisions.py` `determine_decision()`。上から順に評価され、最初にマッチした条件で確定する(decisions.py:36-88)。

1. `BLOCKED` — compliance_status=="blocked"(compliance.py:6-8)
2. `MISSING_DATA` — 必須データ欠落(次項参照)
3. `STALE_DATA` — 国内価格取得後 `maximum_source_data_age_days` 超過、または市場データが `maximum_market_data_age_days` 超過(candidate_rules.yaml由来。サンプル値7日/90日)
4. `REVIEW_COMPLIANCE` — compliance_status in {"review","needs_review"}
5. `LOW_DEMAND` — `sold_90d < minimum_sold_90d` または `sell_through_rate < minimum_sell_through_rate`
6. `LOW_PROFIT` — base利益・base利益率・conservative利益のいずれかが最低基準未満
7. `WATCH` — `confidence_score < minimum_confidence_score`
8. `REPLENISH` / `BUY_TEST_2` / `BUY_TEST_1` — 再仕入履歴/テスト購入履歴/初回購入の順(decisions.py:82-88)

**重要な確認**: `is_first_purchase` / `has_test_purchase_history` / `has_replenish_history` は現状 `opportunity_service.py:253-255` で **常に `is_first_purchase=True`、他2つは常に`False`固定**で呼ばれている。つまり現在のMVPでは、条件を満たすすべての候補が実質的に `BUY_TEST_1` にしかならず、`BUY_TEST_2`/`REPLENISH` へ進める購入履歴トラッキングの実装(それを判定する仕組み)は**未実装**。README/docsのdecision一覧に`BUY_TEST_2`/`REPLENISH`が記載されているが、実際にこの2つが出力されることは現状のコードパスでは起こらない。これは実仕入判断上、重要な制約として利用者に伝える必要がある。

## 4. Matching(商品⇔出品の同一性判定)

実装: `src/opportunity_finder/domain/matching.py` `match_products()`。

- 事前条件: `condition`(new/used)と`unit_count`(セット数)が完全一致しないと即座に不一致(`"none", 0`)(matching.py:29-30) — 型番違い・世代違いは救済されないが、条件・個数違いは確実に弾かれる。
- JAN完全一致 → confidence 100、method="jan"(matching.py:32-33)
- brand+model_numberの正規化(NFKC正規化+casefold)一致 → confidence 90、method="brand_model"(matching.py:35-44)
- 上記どちらもない場合、RapidFuzzの`token_sort_ratio`でタイトル類似度を計算、**90以上**でmethod="fuzzy_title"、90未満は不一致(matching.py:46-48)
- JAN/型番が存在しない商品は、タイトルの表記ゆれに依存したfuzzy matchingのみが頼りになる。ブランド名の表記ゆれ(全角/半角、別名)や、型番のマイナーチェンジ(例: "XYZ-100"と"XYZ-100S")はJAN一致でもbrand_model一致でも救済されず、fuzzy_title側で誤って一致/不一致どちらの方向にもぶれ得る。

data_confidenceスコア(scoring.py:57-103)は上記`match_method`をさらに重み付けし(JAN一致35点、型番一致30点、brand_model一致20点、タイトル類似度90%以上15点)、`condition_mismatch`/`unit_count_mismatch`/`model_number_ambiguous`フラグでそれぞれ-25/-30/-20点の減点を行う。ただしこれらのフラグ自体がどこでセットされるかは`services`層・importer層に依存し、CSV入力側で明示的に付与されない限り機能しない可能性がある(下記5参照)。

## 5. Compliance

実装: `src/opportunity_finder/domain/compliance.py`(is_blocked/needs_review、`product.compliance_status`文字列を見るだけの単純な述語)。

`Product.compliance_status`はDBカラムで、デフォルト値は`'NEEDS_REVIEW'`(db/models.py:55-57、サーバー側default)。products.csvインポーター(`importers/products_csv.py`)には`compliance_status`や`category`列自体が存在せず、CSV経由では設定できない。したがって**新規インポートされた商品はすべて自動的に`NEEDS_REVIEW`として扱われ、`REVIEW_COMPLIANCE`判定でBUYより先に止まる**(decisions.py:58-59が`LOW_DEMAND`等より先に評価されるため)。これは安全側の既定動作であり、CLAUDE.mdの「AIだけで規制判定を承認しない」という制約と整合する。

一方で **`config/risk_rules.yaml`(prohibited_categories / manual_review_categories / require_manual_authenticity_review / require_manual_hs_code_confirmation)は、`src/`・`tests/`のどこからも参照されていないことをgrepで確認した(該当なし)**。つまりこのconfigファイルはドキュメント上の意図表明に留まり、実際のコードパスには一切接続されていない「死んだ設定」である。カテゴリベースの自動レビュー振り分けは実装されておらず、`compliance_status`をレビュー担当者が手動でDBに書き込む運用が前提になっている(その手段=UIやCLIコマンドも現状は存在しない。DB直接更新のみ)。

## 6. Freshness / Stale判定

`decisions.py:50-56`で、`source_data_age_days > maximum_source_data_age_days`(サンプル値7日)または`market_data_age_days > maximum_market_data_age_days`(サンプル値90日)のいずれかで`STALE_DATA`。年齢は`opportunity_service.py:205-206`の`_age_days()`で「計算基準時刻 − captured_at/researched_at」の日数差(`_age_days`はマイナスを0にクランプ、`opportunity_service.py:620-622`)。両方とも`config/candidate_rules.yaml`から読み込まれ、変更可能。

## 7. Confidence(データ信頼度)とBUY抑制の関係

`calculate_confidence_score()`(scoring.py:57-103)の0〜100点は、`WATCH`判定の閾値としてのみ機能する(decisions.py:79-80、`confidence_score < minimum_confidence_score`ならWATCHで打ち止め)。**BUY系判定に到達する前に、必ずLOW_DEMAND(実売データの有無・件数)とLOW_PROFIT(利益基準)の両方を通過する必要がある**ため、「売れた価格データが全くない」候補がBUYまで到達することは、正しくデータが入力されている限りない(`sold_90d`/`sell_through_rate`が必須データとして`MISSING_DATA`でブロックされるため。opportunity_service.py:237-241)。

## 8. eBay Browse APIの現在出品データとProduct Researchデータの関係(重要な確認事項)

**この点はユーザーが特に懸念していた「現在出品価格を実売価格と誤認していないか」に直結する。**

- `MarketResearchMetric`テーブル(db/models.py:157-190)は`source`カラムで由来を区別する(既定値`'PRODUCT_RESEARCH'`、eBay Browse取得時は`'EBAY_BROWSE'`)。
- Product Research CSV(`data/product_research.csv`)は人間が手動取得した実売データ(`sold_count`, `sell_through_rate`, `median_sold_price_usd`等)を`source='PRODUCT_RESEARCH'`として取り込む(importers/product_research_csv.py)。
- **一方、`EbayService._save_active_listing_metric()`(services/ebay_service.py:187-221)は、eBay Browse APIから取得した「現在アクティブな出品」の価格(`item.price_usd`、IQR外れ値除去後)を、同じテーブルの`median_sold_price`/`average_sold_price`カラムに書き込んでいる(ebay_service.py:204-214)。フィールド名は「sold」だが、実際の中身はBrowse APIの現在出品価格(asking price)であり、実売価格ではない。** `sold_count`と`sell_through_rate`はこの呼び出しでは渡されない(デフォルトNone、market_repository.py:162,170)。
- `_latest_market_metric()`(opportunity_service.py:367-381)は、商品ごとに**単一の最新メトリック行**を`researched_at`で選択する(Product ResearchとEBAY_BROWSEをソースで区別せずマージしない、単純に最新1件)。したがって:
  - eBay Browse更新が最新であれば、`market_price`(利益計算のベース)は現在出品価格になる。
  - しかし同じ行の`sold_count`はNoneのため、`has_required_data`チェック(opportunity_service.py:237-241)により**必ず`MISSING_DATA`となり、BUY系判定には絶対に到達しない**(decisions.py:39-48が最優先級で評価されるため)。これは安全側に働く設計であり、確認できた限りでは「現在出品価格だけでBUYが出る」経路は存在しない。
  - ただし、`MISSING_DATA`となった行にも**利益シナリオ自体(net_profit_jpy等)は計算・保存される**(判定がMISSING_DATAでも、その手前で計算は完了している)。エクスポートCSV/JSONLをdecision列でフィルタせずに見る運用をした場合、"median_sold_price"というラベルの数値が実売価格であるかのように誤読されるリスクがある。
  - 副作用として、Product Research取込後にeBay Browse更新を実行すると、その商品の最新メトリックがEBAY_BROWSE行に切り替わり、**それまでBUY判定だった候補が(実売データ自体は変わっていないのに)`MISSING_DATA`に見かけ上ダウングレードされる**。これは誤判定ではなく設計上の安全策だが、運用者が理由を理解していないと「なぜ良い候補が消えた」と混乱する可能性がある。

**結論**: 現状のdecisionロジックはBUY系判定の前提として実売データ(sold_count/sell_through_rate)を要求するガードを持っており、確認した範囲では「現在出品価格のみでBUYが誤って出る」バグは存在しない。ただし(a)フィールド命名(`median_sold_price`)が情報源によって意味が変わる点、(b)MISSING_DATAでも利益数値自体はそのまま保存・エクスポートされる点は、生データを直接見る利用者にとって誤解を招くリスクとして記録する。

## 9. Shipping / Fee / Exchange Rate の入力元

| 項目 | 入力元 | 詳細 |
|---|---|---|
| 国際送料 (`shipping_jpy`) | DB `shipping_rates`テーブル ← `finder import shipping <csv>` | 重量帯(`min_weight_g`〜`max_weight_g`)・仕向国・有効期間で検索(opportunity_service.py:383-397)。サンプル値は`data/samples/shipping_rates.csv`(例: 米国0-500g ¥1,600) |
| マーケットプレイス手数料率 (`variable_fee_rate`, `international_fee_rate`, `ad_rate`, `return_reserve_rate`) | DB `fee_rules`テーブル ← `finder import fees <csv>` または `config/fee_profiles.example.yaml` | カテゴリ・有効期間で検索(opportunity_service.py:399-430) |
| 為替レート | DB `exchange_rates`テーブル ← `finder import exchange <csv>` | `base_currency`/`quote_currency`/`effective_at`で最新値検索(reference_data_repositoryを想定、直接ファイルは未読) |
| シナリオ乗数 (`scenario_multipliers`) | `config/candidate_rules.yaml`が優先、無ければ`config/settings.example.yaml`(opportunity_service.py:515-517) | 楽観/base/悲観の5種の乗数、コードにはハードコードなし |
| 判定閾値 (`minimum_base_profit_jpy`等8項目) | `config/candidate_rules.yaml`必須(opportunity_service.py:524-536で欠落時に例外) | |

すべて**CSV取込またはconfig YAML由来**であり、profit.py/decisions.py自体には金額・料率のハードコードはない(閾値の重み・スコア係数はscoring.pyにハードコードされている、上記2参照)。

## 10. Product Researchデータと現在出品価格の混同リスク(まとめ)

8項で詳述の通り、**コードレベルではProduct Research(実売)とeBay Browse(現在出品)は別の`source`値で区別されているが、フィールド名(`median_sold_price`)は共用されており、どちらの由来でも同じ名前で保存される。** decision判定は`sold_count`欠落によりBUY到達を確実にブロックするため実害は確認されなかったが、生データ・エクスポートCSVを人間が直接読む場面では要注意。

---

## 11. 値の分類表(コード固定 / config / CSV入力 / 外部API由来)

| 値 | 分類 | 根拠(file:line または key) |
|---|---|---|
| Opportunity Score各項目の重み・上限(25/15/15/10/10/10/10/5点、risk減点上限30) | **コード固定** | `domain/scoring.py:26-40` |
| Opportunity Scoreの正規化基準(利益1000円起点/5000円幅、margin 0.10起点/0.40幅、sell-through 0.60、capital efficiency 1.0、conservative利益3000円) | **コード固定** | `domain/scoring.py:26-35` |
| Confidenceスコアの配点(JAN35/型番30/brand_model20/タイトル類似15/市場データ10件+10/データ鮮度7日+5/重量計測5/原産国5、mismatch減点-25/-30/-20) | **コード固定** | `domain/scoring.py:86-100` |
| Matchingのfuzzy title閾値(90) | **コード固定** | `domain/matching.py:47` |
| Matchingのconfidenceスコア(JAN=100, brand_model=90) | **コード固定** | `domain/matching.py:33,44` |
| `minimum_base_profit_jpy`(sample: 3000円) | **config** | `config/candidate_rules.yaml` |
| `minimum_base_margin`(sample: 0.25) | **config** | 同上 |
| `minimum_conservative_profit_jpy`(sample: 1000円) | **config** | 同上 |
| `minimum_sold_90d`(sample: 5) | **config** | 同上 |
| `minimum_sell_through_rate`(sample: 0.15) | **config** | 同上 |
| `maximum_packed_weight_g`(sample: 1000g) | **config(未接続・死んだ設定)** | `config/candidate_rules.yaml`に値は存在するが、`decisions.py`の必須閾値セット(`opportunity_service.py:524-533`、8項目)に含まれず、`product.packed_weight_g`との比較コードもgrepで存在しないことを確認した。読み込まれるが判定に使われない。 |
| `maximum_source_data_age_days`(sample: 7日) | **config** | 同上 |
| `maximum_market_data_age_days`(sample: 90日) | **config** | 同上 |
| `minimum_confidence_score`(sample: 60) | **config** | 同上 |
| シナリオ乗数5種×3シナリオ | **config** | `config/settings.example.yaml` `scenario_multipliers` |
| `prohibited_categories`/`manual_review_categories`等 | **config(未接続・死んだ設定)** | `config/risk_rules.yaml`(コード参照なし、grep確認済み) |
| `variable_fee_rate`/`international_fee_rate`/`fixed_fee_amount`/`ad_rate`/`return_reserve_rate` | **CSV入力(または config sample)** | `finder import fees` ← `data/samples/fee_profiles.csv` / `config/fee_profiles.example.yaml` |
| `shipping_jpy`(重量帯別) | **CSV入力** | `finder import shipping` ← `data/samples/shipping_rates.csv` |
| 為替レート | **CSV入力** | `finder import exchange` ← `data/samples/exchange_rates.csv` |
| 仕入原価・国内送料・ポイント・クーポン | **CSV入力または外部API** | `finder import products` または Yahoo!/楽天API(`clients/yahoo_shopping.py`, `clients/rakuten_*.py`) |
| `median_sold_price`/`sold_count`/`sell_through_rate`(Product Research由来) | **CSV入力(人間手動取得)** | `finder import product-research` ← Product Research CSV |
| `median_sold_price`/`average_sold_price`(EBAY_BROWSE由来、実際は現在出品価格) | **外部API由来(eBay Browse API)** | `services/ebay_service.py:204-214` |
| `compliance_status`(既定NEEDS_REVIEW) | **DBデフォルト(人間が手動更新する前提、CSV/UI経由の更新手段は未実装)** | `db/models.py:55-57` |
| `is_first_purchase`/`has_test_purchase_history`/`has_replenish_history` | **コード固定(常にTrue/False/False)** | `services/opportunity_service.py:253-255` |

---

## 12. Phase 5B: 外部前提調査サマリー

一次情報を優先した調査結果(詳細・出典URL・fact-checker検証結果は [`outputs/research_notes.md`](../outputs/research_notes.md) を参照)。

| 項目 | 調査結果 | 分類 |
|---|---|---|
| eBay標準Final Value Fee | 13.6% + 注文ごと$0.30(≤$10)/$0.40(>$10)。2025-02-14付で最大+0.35%改定 | **verified**(公式ヘルプページで直接確認) |
| eBay International Fee | 約1.65%という値が複数の独立したeBayコミュニティ実例報告と一致するが、公式ページ本文には具体的%の記載を確認できなかった | **configurable assumption**(1.65%は参考値、実運用直前に自アカウントの実請求で要確認) |
| eBay Promoted Listings(CPS) | 出品者が2%〜100%の範囲で任意設定、固定の「標準料率」は存在しない | **user/business-specific** |
| 為替レート運用 | mid-market rateが基準、決済業者スプレッド(実務上1〜3%程度と言われる)。公式固定運用方法はなし | **unverifiable as universal constant** |
| 日本郵便EMS(米国向け第4地帯) | 0.5kg ¥3,900 / 1kg ¥5,300 / 2kg ¥7,900 / 5kg ¥15,100 | **verified**(日本郵便公式サイトで直接確認) |
| 返品率・返品引当 | eBay公式の単一固定値なし。コミュニティ情報でカテゴリ平均5〜8%程度 | **unverifiable as universal constant** |
| 関税・輸入税 | 買い手(輸入者)側の責任が基本。前払い/到着時払いはプログラム次第で、売り手側ツールが確定計算すべき範囲ではない | **user/business-specific** |

## 13. Phase 5C: config値と調査結果の差分評価

| 設定項目 | 現状値(sample) | 意味 | 根拠 | 実運用可能か | 更新要否 |
|---|---|---|---|---|---|
| `variable_fee_rate`(fee_profiles.example.yaml) | 0.1325(13.25%) | eBay最終価値手数料率 | 実装時点の目安値、出典記載なし | 不可 | 要更新。5B検証済みの標準13.6%、またはカテゴリ別実値に置換すべき。`data/samples/fee_profiles.csv`側は0.136(13.6%)で**同一リポジトリ内で2つのサンプルが食い違っている**(example.yaml=13.25% vs samples/fee_profiles.csv=13.6%) |
| `international_fee_rate`(fee_profiles.example.yaml) | 0.0155(1.55%) | eBay越境販売手数料率 | 出典記載なし | 不可(未検証の暫定値) | 要更新方法の明確化。5B調査では公式一次情報で数値を確認できず(1.65%は二次情報の参考値)。`data/samples/fee_profiles.csv`は0.0135(1.35%)で、これも上と同様に2つのサンプル間で不一致 |
| `ad_rate`(fee_profiles.example.yaml, fee_profiles.csv共通) | 0.02(2%) | 広告費(Promoted Listings)率 | Promoted Listingsの最低設定値付近 | 要事業判断 | 更新不要(そもそも「正解値」が存在しない。広告を使うか・料率をいくらにするかは事業者の戦略選択であり、configとしては「デフォルトは広告オフまたは最小値」という設計思想を明示すべき) |
| `return_reserve_rate`(fee_profiles共通) | 0.03(3%) | 返品引当率 | 出典記載なし | 要事業判断 | 更新不要だが、「返品率」ではなく「返品引当(利益からの内部留保)」という会計上の意味を明示する必要がある。普遍的な正解値は存在しない |
| `shipping_jpy`(SAMPLE_US_SMALL, 0-500g) | ¥1,600 | 米国向け国際送料 | 出典記載なし | **不可** | **要更新(重要度: 高)**。5B調査の日本郵便EMS公式0.5kg ¥3,900と比較して**半分以下**。このサンプル値のまま実運用すると、送料原価を過小評価し利益・利益率を過大表示する。EMS以外の実際に使う配送手段(国際eパケット等、より安価な選択肢もある)の実料金に置換が必須 |
| `minimum_base_profit_jpy` / `minimum_base_margin` / `minimum_conservative_profit_jpy` / `minimum_sold_90d` / `minimum_sell_through_rate` / `minimum_confidence_score`(candidate_rules.yaml) | 3000円/0.25/1000円/5/0.15/60 | 判定閾値 | 外部の「正解」が存在しない事業ポリシー値 | 要事業判断 | 更新不要(そもそも外部一次情報で検証できる性質の値ではない。事業者のリスク許容度で決めるべき値) |
| `maximum_source_data_age_days` / `maximum_market_data_age_days`(candidate_rules.yaml) | 7日/90日 | 鮮度閾値 | 事業ポリシー値 | 要事業判断 | 更新不要 |
| `maximum_packed_weight_g`(candidate_rules.yaml) | 1000g | 梱包重量上限(意図) | — | **設定しても効果なし** | コード修正が必要(Phase 5Fで扱う。config更新の問題ではなくコード側の未接続) |
| `prohibited_categories` / `manual_review_categories` 等(risk_rules.yaml) | 食品/化粧品/医薬品/危険物等 | カテゴリ別コンプライアンス振り分け(意図) | — | **設定しても効果なし** | コード側が未接続(Phase 5Fで扱う)。現状の安全性は「全商品が既定でNEEDS_REVIEW」という別経路の安全策で担保されている |

**example/sample値とproduction-ready値の分離**: `config/*.example.yaml`および`data/samples/*.csv`は、ファイル冒頭のコメント(`fee_profiles.example.yaml:1-2`)で「サンプル値である」旨が明記されており、命名(`*.example.yaml`, `data/samples/`)からも実運用値でないことは自明である。実運用時にコピー・置換すべきファイルであることは`README.md`の記述と整合している。**ただし、送料サンプル値がここまで実勢と乖離していること、および同一リポジトリ内の2つのサンプル(config example vs data/samples CSV)が手数料率で食い違っていることは、単なる「サンプルだから未確定」という注意書き以上に、実運用移行時に見落としやすい実害リスクとして今回新たに確認した。**

## 14. Phase 5D: 実データ検証可能性の確認

**結論: リポジトリ内に実市場・実仕入の実データは存在しない。存在するのは`data/samples/`のテスト用サンプル5ファイルのみである。**

確認方法と根拠:
- `data/`配下を再帰的に列挙した結果、`data/samples/`以外にデータディレクトリは存在しない。
- `data/samples/*.csv`の内容は明らかに作成用のテストフィクスチャである: `supplier_url`列はすべて`https://example.invalid/products/...`という予約済みダミードメイン(RFC 2606)、商品名も"Premium Japanese Fountain Pen"等の説明的なサンプル名、`external_key`列も"sample-high-profit-001"のように意図(high-profit/low-profit control)がラベル化されている。
- gitignore対象のランタイム出力`out/opportunities.csv`(過去の実行結果)を確認したところ、含まれる`input_snapshot`のsupplier.price_snapshot、fee_rule.profile_code(`SAMPLE_EBAY_US_DEFAULT`)、shipping_rate.profile_code(`SAMPLE_US_SMALL`)はすべて上記サンプルデータに由来しており、**この出力は過去に`data/samples/`を使ってCLIを試験実行した結果であって、実市場での検証結果ではない**ことが確認できた。
- `.env`(Git管理外)にはテスト用MySQL接続情報が設定されている(PROJECT_STATE.md記載、内容非開示)。これはテストDB接続情報であり、実データの有無を左右するものではない。

したがって、ユーザー指示にある「data/samples/のテストデータを実市場精度の証拠として扱わない」という前提条件どおり、**Phase 5Eの20〜50商品規模の実データ検証はこの時点では実施できない**。存在しないデータを捏造して検証結果とすることも行わない。

Phase 5A・5Cで確認した論理的な検証(利益計算式の健全性、decision優先順位、eBay Browse/Product Researchの分離、config値の妥当性)は実データなしでも実施可能であり、上記1〜13で完了している。これは「実市場での精度が確認された」ことを意味しない — あくまで「ロジックが仕様通りに動く」ことの確認である。

**Phase 5E/5Fは、実データ不足のためスキップする。** 実施するには、利用者から以下のいずれかの提供が必要:
- 実際に仕入候補として検討した国内商品(20〜50件)の実データ(商品名・仕入価格・JAN/型番)
- それに対応する実際のProduct Research結果(実売件数・実売価格・sell-through rate)、または実際のeBay Browse API認証情報(Production access)
- 実際に使う配送方法の実料金表、実際に使う手数料プロファイル(eBayストアプラン等)

*(Phase 5Fは実データ不足のため20〜50商品規模の統計的検証はスキップした。ただしPhase 5A〜5Dの静的監査だけで、Phase 5Fの分類軸のうち「8. scoring/threshold問題」に該当する具体的な確認済みバグを1件発見したため、下記5Gで対応した)*

## 15. Phase 5G: 発見した問題と対応

Phase 5A〜5Dの監査で、実データがなくても静的に確認できる問題が1件見つかった。ただし、この問題の当初の対応(新しいdecision値`OVERSIZED`の追加)はcommit前の独立監査で**既存の一次仕様から導出できない仕様外変更**と判定されたため撤回した。経緯と結論は以下のとおり。

### 未解決の設計課題: `maximum_packed_weight_g` 閾値が判定に一切使われていない

- **カテゴリ**: 8. scoring/threshold問題
- **事象**: `config/candidate_rules.yaml`に`maximum_packed_weight_g: 1000`が定義されているが、`determine_decision()`はこの値を一切参照しておらず、梱包重量が上限を超える候補もCandidate評価をそのまま通過し、他の条件を満たせば`BUY_TEST_1`まで到達し得る。実際、`data/samples/shipping_rates.csv`には1001〜2000gの配送プロファイル(`SAMPLE_US_LARGE`)が別途存在するため、「配送プロファイルがないので自動的に弾かれる」という消極的な安全策も効かないことを確認した。
- **根拠**: `opportunity_service.py`の必須閾値セット(524-533行)に`maximum_packed_weight_g`が含まれていないこと、`decisions.py`のどこにも重量比較コードがないこと、`data/samples/shipping_rates.csv`に1000g超の配送プロファイルが存在することの3点をコードとデータで直接確認した(推測ではない)。設定値自体は`config/candidate_rules.yaml`に残しており、削除していない。
- **なぜPhase 5では実装しなかったか**: `docs/spec.md`[F17]・`docs/design.md`のDecision Literal定義(`BLOCKED`/`MISSING_DATA`/`STALE_DATA`/`REVIEW_COMPLIANCE`/`LOW_DEMAND`/`LOW_PROFIT`/`WATCH`/`BUY_TEST_1`/`BUY_TEST_2`/`REPLENISH`の10値)・`ALL_IN_ONE_SPEC.md`9節の判定例if-elif連鎖・`docs/tasks.md`(T10, 完了基準`F17/S6,S7`)のいずれにも、`maximum_packed_weight_g`超過時の期待挙動(新しいdecisionにするのか、既存decisionに統合するのか、そもそも判定ではなく候補の事前フィルタとして扱うのか)が定義されていない。当初Phase 5Gでは新しいdecision値`OVERSIZED`を追加する実装を行ったが、これは「未接続の既存設定を接続する最小修正」の範囲を超えて、一次仕様に存在しない新しいdecision taxonomy値を独断で決定するものであり、commit前の独立監査(reviewer)で仕様外変更・critical errorと判定されたため、コード変更・テストとも撤回した(`git checkout`で該当ファイルをHEADへ復元)。
- **現状**: `maximum_packed_weight_g`は判定ロジックに未接続のまま、Phase 5終了時点でも未解決である。これは「発見したが直さなかった」のではなく、「直す方法(仕様)が一次資料に存在しないため、architect相当の設計判断なしに実装すべきではないと判断した」という結論である。
- **将来のarchitect判断候補(今回は決定しない)**:
  1. 新しいdecision値を追加する(decision taxonomy自体を仕様変更として拡張し、`docs/spec.md`/`docs/design.md`/`ALL_IN_ONE_SPEC.md`/`docs/tasks.md`を同時に更新する)
  2. 既存decision(例: `LOW_PROFIT`や`WATCH`)に統合し、reason_codeで区別する
  3. 判定ロジックに到達する前の候補抽出段階でのhard filter(超過候補はそもそも計算対象にしない)とする
  4. score計算のrisk_deduction等に反映するsoft filter(除外はしないが機会スコアを下げる)とする
  - いずれも一次仕様に根拠がなく、事業判断(物理的に出荷不能として扱うか、単なるコスト増要因として扱うか)を伴うため、本Phase 5では決定していない。
- **副次的に発見した別の未解決事項**: `ProductInput`/CSVでは`packed_weight_g`(梱包後重量)を受け付けているが、`products`テーブルにはこの列自体が存在せず、`import_service.py`もこの値を一切永続化していない。上記のいずれの案を選ぶ場合でも、この永続化ギャップは別途Alembicマイグレーションで解消する必要がある。

### 対応しなかった項目(evidence-based、変更なしが正しい結果)

| 項目 | 判断 | 理由 |
|---|---|---|
| `config/risk_rules.yaml`が未接続 | **今回は変更しない** | カテゴリ別の自動レビュー振り分けを実装することは、既存の安全な既定動作(新規商品は全件`NEEDS_REVIEW`)の上に新しい自動判定ロジックを追加することになり、「AIだけで規制判定を承認しない」というCLAUDE.mdの制約に照らして、どの粒度で自動化するかは事業者の判断が必要な機能追加である。単純な最小修正の範囲を超えるため、次フェーズの検討事項として記録するに留める(下記16節) |
| eBay Browse由来`median_sold_price`のフィールド命名 | **今回は変更しない** | 現状のdecisionロジックは`sold_count`欠落により、この経路からBUYが誤って出ることを確実に防いでいる(6・8節で確認済み)。フィールド名の変更はDBスキーマ・エクスポート形式に影響する広い変更になるため、実害が確認できていない現時点では見送り、レポートでの明記に留めた |
| `config/fee_profiles.example.yaml`のサンプル手数料率(13.25%/1.55%) | **今回は変更しない** | ファイル自体が`.example.yaml`として明示的にサンプルであり、実運用前の置換が前提の設計。任意の一つの数値に書き換えても「事業者ごとの実際の契約条件」を代表しない。13節の表で現状値と検証結果の差分を明記した |
| `data/samples/shipping_rates.csv`の送料(実勢の半分以下) | **今回は変更しない** | 同上、明示的なテスト用サンプルであり、書き換えても実データにはならない。ただし乖離幅が大きいため13節で強く注意喚起した |
| `is_first_purchase=True`固定(BUY_TEST_2/REPLENISHが事実上出ない) | **今回は変更しない** | 購入履歴トラッキングの実装は新機能追加であり、Phase 5の「検証に紐づかない機能追加をしない」という制約に反する。3節に事実として記録し、次フェーズ候補とする |

## 16. Phase 5H: baseline再検証結果

Phase 5Gの`OVERSIZED`関連コード変更(`domain/decisions.py`, `domain/models.py`, `services/opportunity_service.py`, `tests/unit/test_decisions.py`)は、commit前の独立監査で仕様外変更(critical error)と判定されたため`git checkout`でHEAD(MVP完了時点)へ復元した。したがって以下はMVP baselineそのものの再確認である。

| チェック | 結果 |
|---|---|
| `uv sync` | 成功 |
| `uv run ruff format --check .` | 114 files already formatted(全通過) |
| `uv run ruff check .` | All checks passed! |
| `uv run alembic upgrade head`(実MySQL、リーダー実行) | 成功(エラーなし) |
| `uv run pytest -q`(実MySQL含む全テスト、リーダー実行) | **257 passed**(旧baselineと完全一致、増減なし) |
| `bash scripts/check_no_secrets.sh` | `No tracked .env files or raw-looking secrets detected.`(exit 0) |

**テスト件数について**: `OVERSIZED`用に追加した5テストは、対応するコード変更ごと撤回したため、テストスイートはMVP完了時点の257件のまま変化していない。既存テストの削除・skipは行っていない。

## 17. 次フェーズで検討すべき未解決事項(今回は対応しなかったもの)

1. **`maximum_packed_weight_g`が判定ロジックに未接続**(15節参照)。超過時の期待挙動が一次仕様に定義されていないため、Phase 5では実装していない。architect相当の設計判断(新decision/既存decision統合/hard filter/soft filterのいずれか)が必要。関連して、**`packed_weight_g`がDBに永続化されていない**(products_csv importerは受理・検証するが、`products`テーブルに列がなく`import_service.py`も書き込まない)ため、上記のどの案を選ぶ場合でも別途Alembicマイグレーションが必要。
2. `config/risk_rules.yaml`のカテゴリベース振り分けをどう実装するか(自動化する場合の粒度・承認フロー)は事業判断が必要。
3. `is_first_purchase`/`has_test_purchase_history`/`has_replenish_history`が常に固定値であり、`BUY_TEST_2`/`REPLENISH`が実質使われていない。購入履歴トラッキングの設計・実装が必要。
4. eBay Browse由来の`median_sold_price`/`average_sold_price`フィールドの命名・スキーマ分離(現在出品価格と実売価格を明確に分けるか、少なくともエクスポート形式で警告を出すか)の検討。
5. `config/fee_profiles.example.yaml`・`data/samples/shipping_rates.csv`のサンプル値を、実際に使う予定のeBayストアプラン・配送方法の実料金に置き換える(ユーザー自身の契約条件に依存するため、Claudeが代わりに決定することはできない)。
