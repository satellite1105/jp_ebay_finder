# Phase 6: 実データによる小規模運用試験(Small-Scale Operational Pilot)準備レポート

作成日: 2026-08-09
前提: Phase 5「実運用前検証」完了(commit `21ccf40`)。本レポートはPhase 5の結論を出発点とする。
目的: 実データで20〜50商品規模のpilotを行い、上位候補が実際の仕入判断に使えるかを証拠ベースで検証する。

**重要**: 本レポート作成時点で、リポジトリ内には引き続き実データが存在しない(`data/samples/`のテストフィクスチャのみ、[Phase 5D](operational_validation.md#14-phase-5d-実データ検証可能性の確認)参照)。ユーザーから実データの提供がないため、本フェーズは**Phase 6A〜6Dまでを実施し、6E(pilot実行)以降は「実データ待ち」として停止する**。これは異常ではなく、実データ捏造を避けるための正しい停止点である。

---

## Phase 6A: 現状のread-only確認

### Phase 5の結論(再確認、変更なし)

- コアロジック(利益計算・decision優先順位・matching・freshness/confidence)は仕様どおりに動作することを確認済み。ただし実市場精度は未検証。
- リポジトリ内に実市場・実仕入データは存在しない。`data/samples/`はテスト用フィクスチャのみ。
- `config/fee_profiles.example.yaml`のサンプル手数料率(13.25%/1.55%)と`data/samples/fee_profiles.csv`(13.6%/1.35%)は相互に食い違っており、いずれも実運用値としては未検証。
- `data/samples/shipping_rates.csv`のサンプル送料(米国0-500g ¥1,600)は日本郵便EMS公式(0.5kg ¥3,900)の半分以下で、実運用に使うと利益を過大表示する。
- `config/candidate_rules.yaml`の`maximum_packed_weight_g`(1000g)は判定ロジックに未接続。超過時の期待挙動は一次仕様(`docs/spec.md`/`docs/design.md`/`ALL_IN_ONE_SPEC.md`)に定義がなく、Phase 5では実装せず「未解決の設計課題」として保留(`docs/operational_validation.md` 15節)。
- Decision taxonomyは既存10値(`BLOCKED`/`MISSING_DATA`/`STALE_DATA`/`REVIEW_COMPLIANCE`/`LOW_DEMAND`/`LOW_PROFIT`/`WATCH`/`BUY_TEST_1`/`BUY_TEST_2`/`REPLENISH`)を維持。
- T42 Streamlitは未実装のまま。

### git/baseline確認

- branch: main、origin/mainと同期済み、working tree clean、最新commit `21ccf40 Complete Phase 5 operational validation`
- `uv run pytest -q` → 257 passed / `ruff check`・`ruff format --check` → PASS / `alembic upgrade head` → PASS(下記6Iで再確認)

### 今回必要な「実運用入力」一覧(概要、詳細は6C参照)

1. 実際に使う配送方法の契約送料(shipping_rates.csv形式)
2. 実際のeBay手数料条件(Store契約・カテゴリ別料率、fee_profiles.csv形式)
3. Promoted Listings利用有無・想定広告率
4. 返品引当として採用する事業上の率
5. pilot対象の実商品20〜50件(products.csv形式)
6. 対応するProduct Research実データ(product_research.csv形式)
7. 為替レート(exchange_rates.csv形式)

---

## Phase 6B: 実運用パラメータの分類

分類基準:
- **A**: 公開一次情報から確認可能(すでにPhase 5Bで一次情報・fact-checker検証済み。詳細は[`outputs/research_notes.md`](../outputs/research_notes.md)・[`outputs/phase5b_external_premises.md`](../outputs/phase5b_external_premises.md)参照)
- **B**: ユーザー契約・事業条件に依存
- **C**: ユーザーのリスク許容度に依存
- **D**: 現時点では固定値として定義できない

| # | 項目 | 分類 | 根拠・備考 |
|---|---|---|---|
| 1 | eBay販売手数料(variable_fee_rate) | **A→B** | 標準FVF ~13.6%(2025-02改定)+ 注文ごと$0.30/$0.40はPhase 5Bで一次情報確認済み(A)。ただし実際の料率はStore契約ティア(非Store 13.25%/Basic Store以上 12.35%等)・出品カテゴリで変わるため、ユーザーの実契約(B)を確認しないと確定しない |
| 2 | International Fee等の追加fee | **A→B** | 仕組み・目安値(1.65%、複数二次情報一致)はPhase 5Bで確認済みだが、公式一次情報で数値そのものは未確認(configurable assumption)。適用有無はセラーの配送設定(eBay International Shipping使用可否)に依存(B) |
| 3 | Promoted Listing等の広告費 | **B** | Phase 5Bで「セラー任意設定、固定の標準料率は存在しない」ことを確認済み(user/business-specific)。使うかどうか・料率は事業判断そのもの |
| 4 | 国内→海外送料 | **A→B** | 日本郵便EMS公式レート表(Phase 5Bで直接確認済み)は参考値として使える(A)。ただし実際に使う配送手段(EMS/国際eパケット/フォワーダー/契約割引)はユーザーの選択次第(B) |
| 5 | 国内仕入関連送料 | **B(CSV入力)** | これは固定configではなく、`products.csv`の`source_shipping_jpy`列で商品ごとに入力する設計(既存フォーマット)。仕入先ごとに異なるため一般公開値から定義できない |
| 6 | 為替 | **A(基準レート)/D(スプレッド)** | 仲値(mid-market rate)自体は公開情報から取得可能(A)。決済業者のスプレッド(実務上2.5〜4.5%程度)は公式固定値が存在しない(Phase 5Bでunverifiable as universal constantと結論済み) |
| 7 | 返品引当 | **D** | Phase 5Bで確認済み: eBay公式の単一固定値は存在しない(カテゴリ・商品で5〜8%程度という非公式情報のみ)。事業者が自身の実績に基づき設定すべき値 |
| 8 | 関税・税等 | **A(制度)/D(個別金額)** | 2025年8月の米国de minimis(Section 321)実質廃止という制度変化はPhase 5Bで一次情報確認済み(A)。個々の出荷にかかる実際の関税額はHTSコード・買い手側の状況に依存し、本ツールが確定計算すべき範囲外(D) |
| 9 | candidate threshold(minimum_base_profit_jpy等8項目) | **C** | 外部の「正解」が存在しない事業ポリシー値。事業者のリスク許容度・資金力で決めるべき |
| 10 | stale threshold(maximum_source_data_age_days等) | **C** | 同上。データがどれだけ古くても許容するかは運用ポリシー |

**方針**: A/B項目のうちAで確認済みの参考値は「初期値の目安」としてのみ使用し、実際の計算にはB(ユーザー契約)の値を使う。C/D項目はユーザー自身が事業判断として確定させる必要があり、Claudeが代わりに数値を決定することはしない。

---

## Phase 6C: ユーザー入力が必要な項目(具体的な提供依頼)

以下は、既存資料・一次情報からは確定できず、**ユーザーご自身の事業条件・実データが必須**の項目です。秘密情報(APIキー・パスワード等)の提供は求めていません。

### 1. 配送方法・契約送料 → `shipping_rates.csv`形式
- 何を: 実際に使う予定の配送方法(例: 日本郵便EMS/国際eパケット/フォワーダー等)の重量帯別送料
- 形式: 既存`data/samples/shipping_rates.csv`と同一列構成(`profile_code,destination_country,min_weight_g,max_weight_g,service_name,shipping_jpy,tracking,included_insurance_jpy,effective_from,effective_to`)
- 件数: pilot対象商品の重量帯をカバーする分(目安3〜6行、例: 0-500g/501-1000g/1001-2000g等)

### 2. eBay手数料条件 → `fee_profiles.csv`形式
- 何を: 実際のeBay Store契約ティア(未加入/Basic/Premium等)・出品予定カテゴリの手数料率、International Fee適用有無
- 形式: 既存`data/samples/fee_profiles.csv`と同一列構成
- 件数: 使用予定カテゴリの数だけ(pilotが単一カテゴリ中心なら1行でも可)

### 3. Promoted Listings利用方針
- 何を: 使うかどうか、使う場合の想定広告料率(%)
- 形式: 上記fee_profiles.csvの`ad_rate`列に反映(使わない場合は0)

### 4. 返品引当率
- 何を: 事業上採用する返品引当率(自身の実績、または保守的に見積もる場合の想定値)
- 形式: 上記fee_profiles.csvの`return_reserve_rate`列に反映

### 5. pilot対象の実商品20〜50件 → `products.csv`形式
- 何を: 実際に仕入候補として検討している国内商品(商品名・JAN/型番・仕入価格・重量・仕入先)
- 形式: 既存`data/samples/products.csv`と同一列構成(必須列: `external_key,title,condition,source_cost_jpy,weight_g,origin_country,checked_at`。任意列: `jan,brand,model_number,source_shipping_jpy,packed_weight_g,supplier_name,supplier_url`)
- 件数: 20〜50件

### 6. 対応するProduct Research実データ → `product_research.csv`形式
- 何を: 上記商品に対応する、eBayでの実売実績(手動で取得したsold件数・実売価格・sell-through rate等。CLAUDE.mdの制約によりProduct Researchの自動ログイン取得・スクレイピングは行わないため、人間による手動取得が前提)
- 形式: 既存`data/samples/product_research.csv`と同一列構成
- 件数: 対象商品と対応する分(1商品につき最低1行)

### 7. 為替レート → `exchange_rates.csv`形式
- 何を: pilot時点で使用する実際の為替レート(基準通貨・相手通貨・レート・適用日時)
- 形式: 既存`data/samples/exchange_rates.csv`と同一列構成
- 件数: 1〜数行(通貨ペア・適用期間ごと)

**すでに一次情報や公開資料から判断できる内容についてはご質問していません**(Phase 6B参照)。上記7点は、いずれもユーザーの実際の事業条件・実データがなければ確定できないため、判断不能な項目としてご提示しています。

---

## Phase 6D: 実データ受入フォーマット(既存importer、変更なし)

新しいCSV形式は追加していません。既存の5つのimporterがそのまま使えます。

### products.csv(`finder import products`)
| 項目 | 内容 |
|---|---|
| 必須列 | `external_key, title, condition, source_cost_jpy, weight_g, origin_country, checked_at` |
| 任意列 | `jan, brand, model_number, source_shipping_jpy(既定0), packed_weight_g, supplier_name, supplier_url` |
| 単位 | 金額=円(JPY, Decimal)、重量=グラム(int) |
| 文字コード | UTF-8(BOM可、`utf-8-sig`で読込) |
| 日時形式 | `checked_at`はタイムゾーン付きISO8601必須(例 `2026-08-08T09:00:00+09:00`)。オフセットなしはエラー |
| その他制約 | `condition`は`new`/`used`のみ、`origin_country`は`^[A-Z]{2}$`(2文字大文字国コード)、`jan`は8桁または13桁数字 |
| unique key | `external_key`(同一ファイル内で重複した場合は後勝ち=last-write-wins) |
| 更新方法 | `finder import products <path>` を再実行(ファイルSHA256で処理済み判定、内容が同じなら再取込をスキップ) |

### product_research.csv(`finder import product-research`)
| 項目 | 内容 |
|---|---|
| 必須列 | `external_key, search_query, lookback_days, checked_at` |
| 任意列 | `marketplace(既定EBAY_US), condition, sold_count, active_count, median_sold_price_usd, average_sold_price_usd, median_buyer_shipping_usd(既定0), sell_through_rate, notes` |
| 単位 | 価格=USD(Decimal)、`lookback_days`=日数(int)、`sell_through_rate`=0.0〜1.0の小数 |
| 文字コード | UTF-8(BOM可) |
| 日時形式 | `checked_at`はISO8601 |
| unique key | 全列一致での完全重複行のみ検出・除外(同一`external_key`でも`search_query`/`checked_at`が異なれば別レコードとして許容=複数回の調査履歴を蓄積できる設計) |
| 更新方法 | `finder import product-research <path>` を再実行 |

### shipping_rates.csv(`finder import shipping`)
| 項目 | 内容 |
|---|---|
| 必須列 | `profile_code, destination_country, min_weight_g, max_weight_g, service_name, shipping_jpy, tracking, effective_from` |
| 任意列 | `included_insurance_jpy(既定0), effective_to` |
| 単位 | 金額=円、重量=グラム |
| 制約 | `min_weight_g < max_weight_g`必須、`destination_country`は2文字大文字国コード、`tracking`は真偽値 |
| unique key | 明示的な一意制約はなし(`profile_code`+重量帯+有効期間の組み合わせで、計算時に該当する行が検索・選択される) |
| 更新方法 | `finder import shipping <path>` を再実行 |

### fee_profiles.csv(`finder import fees`)
| 項目 | 内容 |
|---|---|
| 必須列 | `profile_code, marketplace, variable_fee_rate, fixed_fee_currency, fixed_fee_amount, effective_from` |
| 任意列 | `category_code, international_fee_rate(既定0), ad_rate(既定0), return_reserve_rate(既定0), effective_to` |
| 単位 | 手数料率はすべて**比率**(13.6%なら`0.136`、%表記ではない)、`fixed_fee_amount`は`fixed_fee_currency`建ての金額 |
| 更新方法 | `finder import fees <path>` を再実行 |

### exchange_rates.csv(`finder import exchange`)
| 項目 | 内容 |
|---|---|
| 必須列(この5列のみ、他の列は不可) | `base_currency, quote_currency, rate, effective_at` |
| 制約 | 通貨コードは3文字固定(ISO 4217、例 `USD`/`JPY`)。**列が過不足するとファイル全体がエラーになる(他のimporterと異なり未知列を許容しない)** |
| 更新方法 | `finder import exchange <path>` を再実行 |

いずれも既存フォーマットで不足は確認されていません。実データ投入時に不足が判明した場合のみ変更を検討します(今回は変更していません)。

---

## Phase 6E〜6H: 実データ不足のため未実施

`data/samples/`以外に実データが存在しないため(Phase 6A確認済み)、20〜50商品pilot(6E)・人間レビュー(6F)・false positive原因分析(6G)・改善判断(6H)は実施していません。実データを捏造して先に進むことはしていません。

Phase 6Cで提示した7項目のデータが揃い次第、次回セッションで6E以降を再開できます。

---

## Phase 6I: baseline再確認

コード変更は行っていない(このフェーズはドキュメント作成のみ)。以下は変更なしの状態での再確認結果。

| チェック | 結果 |
|---|---|
| `uv run ruff format --check .` | 114 files already formatted(全通過) |
| `uv run ruff check .` | All checks passed! |
| `uv run alembic upgrade head`(実MySQL) | 成功 |
| `uv run pytest -q`(実MySQL含む) | **257 passed**(既存baselineと完全一致、増減なし) |
| `bash scripts/check_no_secrets.sh` | 検出なし |

コード変更がなかったため、baselineに変化はない。既存テストの削除・skipは行っていない。
