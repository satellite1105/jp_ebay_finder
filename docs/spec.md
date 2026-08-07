# 要件定義: Japan eBay Opportunity Finder

## 目的(1〜2文)
日本国内の仕入価格と海外(主にeBay)販売データを比較し、送料・手数料・関税/通関処理費・広告費・返品引当まで差し引いた予想純利益を再現可能な決定論的ロジックで計算し、高利益な仕入れ候補をランキングするツールを構築する。感覚ではなくデータで仕入判断を行えるようにすることが目的であり、自動購入・自動出品は行わない。

## 想定ユーザーと利用シーン
- 日本在住の小規模越境EC事業者(初期資金3万〜10万円程度)
- eBayを最初の販売先とする
- 既存MySQLとVPSを保有し、それを流用したい
- AI・自動化を部分的に活用したいが、最終判断は人間が行いたい
- 利用シーン: 日次バッチ(systemd timer)で国内価格・市場データを更新し、CLIまたはCSVで上位候補を確認し、Product Researchで裏取りしてから少量テスト仕入れを判断する。

## 機能要件

### must(これがないと成立しない)

#### Phase 0: 基盤
- [F1] `uv` による依存関係管理、`pyproject.toml`/`uv.lock` を整備する
- [F2] Ruff (`format --check` / `check`) が通る状態を維持する
- [F3] pytest が実行できる状態を整備する
- [F4] `pydantic-settings` で `.env` からMySQL接続設定・APIキー等を読み込む(`.env`はGit管理しない)
- [F5] 構造化ログを出力し、APIキー・Authorizationヘッダー・MySQLパスワードをマスクする
- [F6] Typer製CLI `finder` の骨組みを作り `finder --help` が動作する

#### Phase 1: オフラインMVP(外部APIなしで完動すること)
- [F7] SQLAlchemy 2.x + Alembicで既存MySQL(`ebay_opportunity` DB、既定名は環境変数で変更可)へ接続し、マイグレーションで初期スキーマを作成する(`finder db check` / `db upgrade` / `db current`)
- [F8] 国内商品CSV (`products.csv`) を取り込み、`products` / `supplier_items` / `supplier_price_snapshots` へ保存する
- [F9] Product Research手動CSV (`product_research.csv`) を取り込み、`market_queries` / `market_research_metrics` へ保存する
- [F10] 送料表CSV (`shipping_rates.csv`)、手数料表CSV (`fee_profiles.csv`)、為替CSV (`exchange_rates.csv`) を取り込む
- [F11] CSV取込はSHA-256ハッシュ等により冪等性を担保し、同一ファイル・同一行の再取込で重複を作らない(不正行・不正列はファイル/行単位で隔離し他行の処理を継続する。Excel数式インジェクション対策を含む)
- [F12] `decimal.Decimal` によるMoneyドメイン(通貨換算・丸め処理)を実装し、金額をfloatで扱わない
- [F13] Optimistic / Base / Conservative の3シナリオで利益計算を行う(03_PROFIT_AND_SCORING.md の計算式・乗数どおり)
- [F14] 損益分岐価格(`break_even_price_usd`)と目標利益達成価格(`target_price_usd`)を算出する
- [F15] データ信頼度スコア(0〜100)を算出し、`confidence_score < 60` は自動仕入れ候補にしない
- [F16] 機会スコア(0〜100、内訳付き)を算出し、内訳(根拠値)もDBへ保存する
- [F17] 候補判定ステータス(`BLOCKED` > `MISSING_DATA` > `STALE_DATA` > `REVIEW_COMPLIANCE` > `LOW_DEMAND` > `LOW_PROFIT` > `WATCH` > `BUY_TEST_1`/`BUY_TEST_2` > `REPLENISH`)を優先順位どおりに実装する
- [F18] `finder calculate opportunities` / `finder calculate opportunity --product-id` / `finder calculate break-even --product-id` を実装する
- [F19] `finder report top --limit N [--decision X] [--format table]` で上位候補をCLI表示する
- [F20] `finder export opportunities <path>` / `finder export audit <path>` でCSV/JSONLエクスポートする
- [F21] 監査ログ(`audit_logs`)を残し、計算結果だけでなく計算に使った前提値・入力スナップショットも保存する(`opportunity_snapshots.input_snapshot`等)
- [F22] E2Eサンプル一式(サンプルCSV→DB upgrade→import→calculate→report→export)がエラーなく通ること

#### Phase 2: 国内API連携
- [F23] Yahoo!ショッピング商品検索v3クライアントを実装する(検索順: `jan_code` → `query`)
- [F24] 楽天市場商品検索API(Ichiba Item Search)クライアントを実装する
- [F25] 楽天製品検索API(Product Search)クライアントを実装する
- [F26] httpxベースの共通APIクライアント(timeout、429/5xx限定リトライ+exponential backoff+jitter、request ID保存、認証情報マスク、raw payload保存、レスポンススキーマ検証)を実装する
- [F27] JAN完全一致 → ブランド+型番一致 → RapidFuzzによるタイトル類似度、の順でマッチングを行い、セット数・状態(新品/中古)の不一致は誤マッチとして除外する
- [F28] API障害時(timeout/429/5xx)でも既存データを用いてランキング計算を継続できること
- [F29] 送料込み実質価格(最安値ではなく)を `effective_cost_jpy` として保存する

#### Phase 3: eBay Browse API連携(任意有効化・フォールバック必須)
- [F30] eBay Browse APIをClient Credentials(Application Token、トークンキャッシュ)経由で利用し、keyword/GTIN検索・ページネーション(`next`優先)に対応する
- [F31] Production access未承認・403・権限不足時は自動的にCSVモード(現在出品CSV/Product Research CSV)へフォールバックし、処理を止めない
- [F32] 廃止済みFinding API/Shopping API、非公開のMarketplace Insights APIは使用しない
- [F33] 出品価格・送料・condition・seller country等を正規化して保存し、外れ値除外後の中央値と競合件数を計算する。`total`件数を厳密な競合数として盲信しない

#### Phase 4: 運用
- [F34] `finder daily --stale-only --export-dir <dir>` で日次処理(DB接続確認→設定検証→為替更新→古い国内価格更新→eBay更新(利用可能な場合)→Product Research新規CSV取込→機会スナップショット計算→上位候補CSV出力→実行サマリー出力→失敗件数閾値超過時は非0終了)を実装する
- [F35] systemd service/timerで日次自動実行できるデプロイ設定(`deploy/systemd/`)を用意する
- [F36] `scripts/backup_mysql.sh` によるMySQLバックアップ(`mysqldump --single-transaction`)を用意する
- [F37] GitHub ActionsでCI(lint/test、MySQLサービスコンテナ使用、本番シークレット不使用)を構成する

### nice-to-have(今回はスコープ外でも可)
- [N1] Streamlit管理画面(候補ランキング、商品詳細、コスト内訳、3シナリオ比較、手動Product Research入力、規制承認/却下、仕入れ済みフラグ、CSVダウンロード)。CLI+DBだけでも運用可能な設計を維持し、Streamlitを唯一の管理手段にしない
- [N2] 実績利益の取込・予測誤差集計(送料・関税・返品損失の月次見直し、SKU別補充判定)
- [N3] Slack Webhook通知
- [N4] pyright等による型チェックのCI追加

## 非機能要件
(既存資料に明記された制約を反映。指示にないものは仮定として明示)

### データ・DB
- 既存MySQL 8.0以上(InnoDB、`utf8mb4`)のみを使用し、PostgreSQL/DuckDB/Supabase/Elasticsearch/Redis等の新規DB・ミドルウェアは導入しない
- 専用DB名は既定 `ebay_opportunity`、環境変数で変更可能
- MySQL 5.7/MariaDBの場合は非対応箇所を検出し明示する(実装前に `mysql --version` / `SELECT VERSION()` で確認)
- スキーマ変更はAlembic migrationでのみ行い、破壊的マイグレーション(カラム削除等)は自動実行しない。カラム削除は2段階で行う
- 金額は `DECIMAL(18,4)`(外貨は`DECIMAL(18,6)`程度)、率は`DECIMAL(10,6)`、日時は`DATETIME(6)`でUTC保存、表示時のみAsia/Tokyoへ変換する。金額計算・保存に`float`を使わない
- 生のAPIレスポンスはJSON列で保存する

### セキュリティ
- APIキー・トークン・パスワードをソースコード・Markdown・ログ・DBへ保存しない。`.env`はGit管理しない
- MySQLをインターネットへ公開せず、アプリはroot権限で実行しない。DBユーザーは最小権限とする
- CSV出力時は `=`, `+`, `-`, `@` で始まるセルを無害化する(数式インジェクション対策)
- 外部APIレスポンスはPydanticで検証し信用しない
- 依存パッケージの定期監査を行う

### 可用性・信頼性
- 外部API(Yahoo/楽天/eBay)が利用不可でも、CSV+既存DBデータのみでMVPの一連の処理(取込→計算→ランキング出力)が完動すること
- eBay Browse APIが未承認・利用不可でも全体は動作すること(必須要件ではなく任意強化)
- API障害時の挙動を明文化する(05_OPERATIONS_AND_SECURITY.md 表参照): timeout/429はリトライ後に既存データ利用、eBay 401はトークン再取得1回のみ、eBay 403/権限不足はCSVモードへ、MySQL接続失敗は書き込みせず非0終了、CSV不正はファイル単位で隔離
- 同一入力の再実行は冪等(重複レコードを作らない)であること

### 計算の正確性・監査性
- 利益・利益率・判定はPythonの決定論的ロジックのみで行い、LLM/AIには委ねない
- 手数料率・送料・為替・判定基準値をコードへ直書きせず、設定ファイル(YAML)またはDBで変更可能にする
- 計算結果だけでなく計算に用いた前提値(為替、手数料率、送料表バージョン等)も保存し、1候補の計算根拠を追跡できること

### ログ・監視
- ログは構造化し、timestamp/level/run_id/command/source/product_id/query_id/elapsed_ms/status/error_type/retry_count/rows_read/rows_writtenを含める
- 日次処理ごとに`run_id`を発行しDBと結びつける

### コンプライアンス
- 規制・真贋・危険物・HSコード最終確定・仕入れ自動発注・返金/紛争対応をAIに任せない
- 食品・化粧品・医薬品・危険物等は自動承認せず、`compliance_status`が`blocked`/`review`の商品は`BLOCKED`/`REVIEW_COMPLIANCE`として扱う

## データ要件(要点。詳細DDLは `docs/01_ARCHITECTURE_AND_DATABASE.md` を正とする)
- 主要テーブル: `products`(商品マスタ) / `supplier_items`・`supplier_price_snapshots`(国内仕入先・価格履歴) / `market_queries`・`market_research_metrics`(eBay検索条件・Product Research実績) / `ebay_listings`・`ebay_listing_snapshots`(eBay出品識別・現在価格履歴) / `exchange_rates`(為替履歴) / `shipping_rates`(送料表) / `fee_rules`(手数料・引当ルール) / `opportunity_snapshots`(計算結果履歴) / `scan_runs`(バッチ実行履歴) / `import_batches`(CSV取込履歴) / `audit_logs`(手動変更監査)
- `ENUM`型は原則使わず、`status`等は`VARCHAR(32)`で表現する(migrationの柔軟性維持のため)
- インデックス方針: 最新取得は`(entity_id, captured_at)`、ランキングは`(scenario, decision, opportunity_score)`、商品照合はJAN/ブランド+型番、JSON内の頻出値は通常列へ昇格
- 動作モード: Mode A(Full API: Yahoo+楽天+Browse API+Product Research CSV) / Mode B(No eBay API: Yahoo+楽天+eBay出品CSV+Product Research CSV) / Mode C(Offline: 国内CSV+eBay CSV+Product Research CSV+手動為替+手動送料表)。すべてのテストはMode Cで実行可能であること

## 利益計算・高利益判定基準(既存資料の数値をそのまま転記)

### 金額計算の原則
- `decimal.Decimal`を使用し、`float`を利益計算に使わない
- 為替・手数料率・税率は計算日時点のスナップショットとして保存する
- 計算後の結果だけでなく使用した前提値も保存する

### 基本計算式
```text
buyer_total_usd = item_price_usd + buyer_shipping_usd
recognized_revenue_jpy = buyer_total_usd × exchange_rate_jpy_per_usd
variable_marketplace_fee_jpy = fee_base_jpy × marketplace_fee_rate
marketplace_fee_jpy = variable_marketplace_fee_jpy + marketplace_fixed_fee_jpy
promoted_listing_jpy = ad_fee_base_jpy × promoted_listing_rate
return_reserve_jpy = recognized_revenue_jpy × return_reserve_rate

total_cost_jpy =
  source_item_cost_jpy + source_domestic_shipping_jpy + source_transport_jpy
  + packaging_jpy + international_shipping_jpy + duty_jpy + import_processing_jpy
  + marketplace_fee_jpy + international_fee_jpy + currency_conversion_jpy
  + promoted_listing_jpy + payment_fee_jpy + return_reserve_jpy
  + labor_cost_jpy + other_cost_jpy

net_profit_jpy = recognized_revenue_jpy - total_cost_jpy
net_margin = net_profit_jpy / recognized_revenue_jpy
capital_efficiency = net_profit_jpy / cash_required_before_sale_jpy
```
`fee_base_jpy`はプラットフォーム規約に合わせて可変(商品代のみ/購入者送料含む等)にする。

### 返品期待損失(MVP方式)
```text
return_reserve_jpy = revenue_jpy × return_reserve_rate
```
初期値2〜4%を設定ファイルで指定可能にする(コード直書き禁止)。実績30件未満の場合はカテゴリ既定値と実績値を加重平均する実績方式も用意する。

### 三つの採算シナリオと推奨初期乗数
| シナリオ | 売価倍率 | 為替倍率 | 送料倍率 | 広告倍率 | 返品倍率 |
|---|---|---|---|---|---|
| Optimistic | 1.05 | 1.02 | 0.95 | 0.70 | 0.70 |
| Base | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Conservative | 0.92 | 0.97 | 1.10 | 1.30 | 1.50 |

仕入れ判定ではBaseだけでなくConservativeも確認する。

### 損益分岐・目標価格
```text
break_even_revenue_jpy = fixed_cost_jpy / (1 - total_variable_rate)
break_even_buyer_total_usd = break_even_revenue_jpy / exchange_rate_jpy_per_usd
target_revenue_jpy = (fixed_cost_jpy + target_profit_jpy) / (1 - total_variable_rate)
```

### 高利益判定基準(初期値。設定ファイル/DBで変更可能、コード直書き禁止)
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

### 判定ステータス(優先順位順)
`BLOCKED` > `MISSING_DATA` > `STALE_DATA` > `REVIEW_COMPLIANCE` > `LOW_DEMAND` > `LOW_PROFIT` > `WATCH` > `BUY_TEST_1`/`BUY_TEST_2` > `REPLENISH`

00_PROJECT_BRIEF.md記載の判定種類(表示用途):
| 判定 | 意味 |
|---|---|
| `BUY_TEST_1` | 1個だけテスト仕入れ候補 |
| `BUY_TEST_2` | 最大2個までテスト候補 |
| `WATCH` | 価格変化を監視 |
| `NEEDS_RESEARCH` | 販売済みデータ等が不足 |
| `REJECT_LOW_PROFIT` | 利益不足 |
| `REJECT_LOW_DEMAND` | 需要不足 |
| `REJECT_RISK` | 規制・真贋・危険物等 |
| `REJECT_STALE_DATA` | データが古い |
| `BLOCK` | 扱わない |

### 機会スコア(0〜100点)
| 要素 | 配点 |
|---|---:|
| Base純利益 | 25 |
| Base利益率 | 15 |
| 90日販売数(対数変換) | 15 |
| Sell-through rate | 10 |
| 資金効率 | 10 |
| Conservative耐性 | 10 |
| データ信頼度 | 10 |
| 継続仕入れ | 5 |
| リスク控除 | 〜-30 |

### データ信頼度配点
JAN完全一致+35 / メーカー型番完全一致+30 / ブランド+型番一致+20 / タイトル類似度90%以上+15 / 市場データ10件以上+10 / 国内価格7日以内+5 / 重量実測+5 / 原産国実物確認+5 / 商品状態不一致-25 / 内容量・セット数不一致-30 / 型番曖昧-20。0〜100へ丸め、60未満は自動仕入れ候補にしない。

### 禁止事項
- LLMへ利益計算を委ねない / 手数料率をコードへ直書きしない / 古い市場価格を現在値として扱わない / 商品価格だけを見て利益判定しない / 「売れた件数不明」を0件または推定値で埋めない / 原産国不明を日本製として扱わない / 商品状態やセット数が異なる競合を同一比較しない

## 受け入れ条件・成功条件

### MVP受入条件(すべて満たすこと)
- [S1] 既存MySQL以外のDBを一切必要としない(コード・設定・依存関係にPostgreSQL/DuckDB/Supabase/Elasticsearch/Redisが含まれないことをコードレビューで確認可能)
- [S2] 外部API(Yahoo/楽天/eBay)を一切呼ばない状態(Mode C)でも、サンプルCSV(`data/samples/`)から `finder db upgrade` → `import` 4種 → `finder calculate opportunities` → `finder report top` → `finder export opportunities` の一連のE2Eコマンドがエラーなく完了する
- [S3] 利益計算のUnitテストにおいて、手計算した基準ケース(正常系・赤字・固定手数料込み・広告費込み・関税込み・返品引当込み)と1円以内で一致する
- [S4] 同一入力(同一CSV・同一設定)で `finder calculate opportunities` を2回実行しても `opportunity_snapshots` の計算結果(金額・スコア・判定)が同一になる(再現性)
- [S5] 3シナリオ(Optimistic/Base/Conservative)と損益分岐価格(`break_even_price_usd`)が候補ごとに算出され、DBに保存される
- [S6] `compliance_status = blocked` の商品は、他の条件に関わらず判定が必ず `BLOCKED` となり、`finder report top` の出力(BUY_TEST系)に一切現れない(Decisionドメインのpytestで優先順位を検証)
- [S7] Product Research等の販売済みデータが不足する候補は `MISSING_DATA` または `NEEDS_RESEARCH`(表示用途)として扱われ、「高利益確定」として表示されない
- [S8] eBay Browse APIキー未設定・403・権限不足の状態でも `finder daily` が非0終了せず完了し、CSVモードにフォールバックしたことがログ・監査ログから確認できる
- [S9] 同じCSVファイルを2回取り込んでも `import_batches`/`supplier_price_snapshots` 等に重複レコードが作られない(ハッシュベースの冪等性)
- [S10] CIで `uv run ruff format --check .` / `uv run ruff check .` / `uv run alembic upgrade head`(MySQLコンテナ対象) / `uv run pytest -q` がすべて成功する
- [S11] ドメインロジック(Money/Profit/Scoring/Decisions/Matching)のテストカバレッジ90%以上、全体80%以上
- [S12] CSV出力の全金額列を手計算で合計すると `total_cost_jpy` と一致する(コスト内訳の説明可能性)
- [S13] `.env`・APIキー・トークンがGitリポジトリ・ログファイル・DBのいずれにも含まれない(grepベースのセキュリティチェックで確認)

### テスト戦略(reviewerが採点する対象)
- Unitテスト: Money(Decimal変換・丸め・float拒否)、Profit(正常系/固定手数料/広告なし/関税なし/赤字/0除算回避/Conservative/損益分岐)、Scoring(上限下限/0件/高利益低需要/低利益高需要/リスク控除)、Decisions(BLOCKED最優先/データ不足/データ鮮度/BUY_TEST_1・2/REPLENISH)、Matching(JAN完全一致/型番一致/セット数違い/新品中古違い/RapidFuzz類似度/ブランド誤一致)
- CSVテスト: 正常ファイル/必須列欠落/重複行/文字コード/不正日付/不正数値/数式インジェクション対策/途中失敗時のトランザクション
- API contract テスト(respx/MockTransport): 200/204/400/401/403/404/429/500-502-503/timeout/不正JSON/pagination/レート制限ヘッダー/eBay権限不足時のCSVフォールバック
- MySQL統合テスト(テスト専用MySQL、SQLiteで代用しない): Alembic upgrade/downgrade、一意制約、外部キー、トランザクションrollback、upsert、同時更新、主要クエリのインデックス利用(EXPLAIN)
- E2Eテスト: サンプルCSV一式からの一気通貫実行、コスト内訳合計の一致、BLOCKED商品が購入候補に出ないことの確認

## 前提と仮定(既存資料に明記されていないため実装のために置く必要がある仮定)

既存資料(特にCLAUDE.mdと00〜06)は非常に詳細であり、判定基準・DB設計・計算式・CLI仕様・OSS選定まで具体的数値付きで明記されているため、新たに置く仮定はごく僅かである。以下は実装を進める上で不可避的に生じる、資料に明記のない軽微な運用上の仮定のみである。

- [A1] **spec.mdのファイル配置**: 資料一式は既に極めて詳細なため、spec.mdは新規の設計判断を行わず、既存資料(docs/00〜06, IMPLEMENTATION_CHECKLIST.md, SOURCE_REFERENCES.md)の内容を要件定義書フォーマットへ構造化・転記したものとする。理由: タスク指示により「既存資料を正とし、矛盾する新しい設計判断を持ち込まない」ことが明示されているため。
- [A2] **プロジェクト名の英語表記**: リポジトリ名/CLI名として `Japan eBay Opportunity Finder` / `finder` を採用する。理由: README.mdおよび04_IMPLEMENTATION_AND_TESTS.mdの推奨リポジトリ構成・CLI名をそのまま踏襲したため、新規の命名判断ではない。
- [A3] **spec.md自体の格納先バージョン管理**: `docs/spec.md` はdev-factoryのautodevパイプラインにおけるフェーズ1成果物として扱い、以降のフェーズ2(design.md/tasks.md)がこのファイルのF1〜F37, S1〜S13のIDを参照する前提とする。理由: dev-factory運用ルール(PROJECT_STATE.md記載)に基づく形式要件であり、既存資料には元々spec.mdという成果物区分が存在しないため。
- [A4] **成功指標の定量化**: 00_PROJECT_BRIEF.mdの成功指標(「CSV取込100件をエラーなく処理」等の定性的記述)を、reviewerが採点可能な検証可能形式(S1〜S13)へ具体化した。理由: 既存資料の成功指標はacceptance criteriaとしてはやや抽象的なため、04_IMPLEMENTATION_AND_TESTS.mdの「受入条件」「品質ゲート」節の記述と統合し、数値・確認手段を明記する形に落とし込んだ。数値基準自体(90%/80%カバレッジ、0.85 reviewerスコア等)は既存資料またはdev-factory運用ルールに由来し、新規の基準は作っていない。

これら以外の判断(DB選定、金額型、判定基準値、手数料計算式、CLI仕様、OSS選定、禁止事項等)はすべて既存資料の明記内容をそのまま採用しており、独自の仮定は置いていない。

## スコープ外(明示的にやらないこと)
- 商品の自動購入・自動発注
- eBayへの自動出品
- eBay Product Researchへの自動ログイン取得・CAPTCHA回避・ブラウザ指紋偽装・アクセス制限回避
- eBay HTMLの大量スクレイピング(非公式スクレイパー・Selenium/Playwrightの中核データ取得への利用を含む)
- 廃止済みのeBay Finding API / Shopping APIの利用
- 新規利用者に開放されていないeBay Marketplace Insights APIを前提とした設計
- 食品、化粧品、医薬品、危険物等のAIによる自動承認・最終規制判定
- AIによる真贋判定・HSコードの最終確定・返金/紛争対応
- 新しいDB(PostgreSQL、DuckDB、Supabase、Elasticsearch)、Redis、メッセージキュー、Airflow/Dagster/Prefect等の重量級OSS基盤の導入
- Streamlit画面をMVPの必須要件とすること(任意のnice-to-haveとする)
- 本番環境への自動デプロイ・外部公開

## 参照元(SOURCE_REFERENCES.md より引用)

基準日: 2026-08-06。実装時は必ず公式ドキュメントを再確認すること。API仕様、料金、利用条件は変更される。

### MySQL
- MySQL 8.4 Reference Manual — JSON_VALUE and expression indexes: https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html
- MySQL 8.4 Reference Manual — Indexes on Generated Columns: https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html
- MySQL 8.4 Reference Manual — Multiple-Column Indexes: https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html

### eBay
- Browse API overview: https://developer.ebay.com/api-docs/buy/browse/overview.html
- Browse API search method: https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
- Product Research: https://www.ebay.com/help/selling/selling-tools/product-research?id=4853
- Marketplace Insights API overview: https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html
- Buy APIs production eligibility / approval: https://developer.ebay.com/api-docs/static/gs_ebay-rest-getting-started-landing.html
- eBay API deprecation status: https://developer.ebay.com/develop/get-started/api-deprecation-status
- Finding API decommission notice: https://developer.ebay.com/develop/apis/deprecated
- Official eBay OAuth Python client repository: https://github.com/eBay/ebay-oauth-python-client
- Archived unofficial Browse API Python client(採用しない): https://github.com/AverHLV/browseapi

### Yahoo!ショッピング
- Yahoo!デベロッパーネットワーク ショッピング商品検索v3: https://developer.yahoo.co.jp/webapi/shopping/shopping/v3/itemsearch.html

### 楽天
- 楽天市場商品検索API: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
- 楽天製品検索API: https://webservice.rakuten.co.jp/documentation/ichiba-product-search

### Python / OSS
- SQLAlchemy: https://github.com/sqlalchemy/sqlalchemy
- Alembic: https://github.com/sqlalchemy/alembic
- HTTPX: https://github.com/encode/httpx
- Pydantic: https://github.com/pydantic/pydantic
- Pydantic Settings: https://github.com/pydantic/pydantic-settings
- Tenacity: https://github.com/jd/tenacity
- RapidFuzz: https://github.com/rapidfuzz/RapidFuzz
- Typer: https://github.com/fastapi/typer
- Rich: https://github.com/Textualize/rich
- Streamlit: https://github.com/streamlit/streamlit
- uv: https://github.com/astral-sh/uv
- Ruff: https://github.com/astral-sh/ruff
- pytest: https://github.com/pytest-dev/pytest

### 採用上の注意
- GitHubのstar数だけで採用しない
- 最終リリース、コミット頻度、Issue、Python対応版を確認する
- 公式SDKでも対象Pythonが古い場合は採用しない
- 非公式eBayスクレイパーは更新停止・規約違反・HTML変更リスクが高いため中核へ使わない
- 依存パッケージは最小限にし、ロックファイルをコミットする
