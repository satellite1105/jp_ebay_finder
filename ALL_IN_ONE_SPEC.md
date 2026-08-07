# Japan eBay Opportunity Finder — 一括仕様書

このファイルは、分割された開発資料をClaude Codeへ一括で渡すために連結したものです。各章の正本は個別Markdownです。


---

<!-- BEGIN: README.md -->
# Japan eBay Opportunity Finder — 開発資料一式

基準日: 2026-08-06

## 結論

既存の **MySQLをそのまま利用**する。DuckDB、PostgreSQL、Supabaseなどの新規DBは導入しない。

このプロジェクトは、日本国内の仕入価格と海外販売データを比較し、送料・手数料・関税・返品引当まで差し引いたうえで、仕入れ候補をランキングするツールである。

## 最重要の制約

1. eBay Finding API / Shopping APIは廃止済み。
2. eBay Browse APIの本番利用には申請・承認が必要。
3. eBay Marketplace Insights APIは新規利用者に開放されていない。
4. eBay Product Researchの販売済みデータは、MVPではCSV手入力・手動インポートで補完する。
5. CAPTCHA回避、ログイン回避、非公式な大量スクレイピングは実装しない。
6. Browse APIが使えなくても、国内API＋Product Research CSVだけで動作すること。

## 最初に読む順番

1. `CLAUDE.md`
2. `docs/00_PROJECT_BRIEF.md`
3. `docs/01_ARCHITECTURE_AND_DATABASE.md`
4. `docs/02_DATA_APIS_AND_OSS.md`
5. `docs/03_PROFIT_AND_SCORING.md`
6. `docs/04_IMPLEMENTATION_AND_TESTS.md`
7. `docs/05_OPERATIONS_AND_SECURITY.md`
8. `docs/06_CLAUDE_CODE_EXECUTION_PROMPT.md`
9. `IMPLEMENTATION_CHECKLIST.md`
10. `SOURCE_REFERENCES.md`

## MVPの完成形

```text
国内商品CSV / Yahoo!ショッピングAPI / 楽天API
                    ↓
              商品名・JAN正規化
                    ↓
eBay Browse API（承認済みの場合） ─┐
Product Research CSV（必須）      ├→ MySQL
手動候補CSV                       ─┘
                    ↓
       送料・手数料・為替・関税計算
                    ↓
         高利益候補ランキング
                    ↓
       CSV / CLI / 任意のStreamlit画面
```

## 最初の高利益判定基準

```text
予想純利益        3,000円以上
純利益率          25%以上
90日販売数        5件以上
Sell-through      15%以上
梱包後重量        1,000g以下
規制判定          BLOCKでない
仕入データ鮮度    7日以内
販売データ鮮度    90日以内
```

基準は設定ファイルまたはDBで変更可能にする。コードへ直書きしない。

## 推奨実装順

1. MySQL接続・マイグレーション
2. CSV取込
3. 利益計算
4. ランキング
5. Yahoo!ショッピングAPI
6. 楽天API
7. eBay Browse APIアダプター
8. CLI
9. 定期実行
10. Streamlit画面（任意）

## 開発原則

- 数値計算はDecimalで行う
- 金額をfloatで保持しない
- 元APIレスポンスをJSONで保存する
- 計算結果だけでなく計算前提も保存する
- APIが失敗しても既存データで再計算できる
- 1商品の仕入判断に至った根拠を追跡できる
- AIは名称正規化や検索語候補生成の補助に限定し、利益計算は決定論的に行う

<!-- END: README.md -->

---

<!-- BEGIN: CLAUDE.md -->
# Claude Code向けプロジェクト指示

## 役割

あなたは、既存MySQLを利用した「日本商品の海外販売機会発掘ツール」を実装するシニアPythonエンジニアです。

## 最初に必ず行うこと

1. このファイルを読む。
2. `docs/`配下を番号順に読む。
3. 現在のリポジトリ構成、Python、MySQL、Gitの状態を確認する。
4. 既存ファイルを勝手に削除・置換しない。
5. 実装前に、今回変更するファイルと実装順を簡潔に提示する。
6. 各フェーズ終了時にテストを実行する。

## 絶対条件

- DBは既存MySQLを使う。
- 新しいPostgreSQL、DuckDB、Supabase、Elasticsearchは導入しない。
- 本番MySQLの既存テーブルへ勝手に変更を加えない。
- 専用DB名は既定で `ebay_opportunity` とし、環境変数で変更可能にする。
- MySQL 8.0以上を標準対象とする。
- MySQL 5.7またはMariaDBの場合は、非対応箇所を検出して明示する。
- 金額計算は `decimal.Decimal` を使う。
- 金額・率をfloatで保存しない。
- APIキーをソース、Markdown、ログ、DBへ保存しない。
- `.env` はGit管理しない。
- CAPTCHA回避、ブラウザ指紋偽装、アクセス制限回避を実装しない。
- eBay HTMLを大量スクレイピングしない。
- Product Researchの自動ログイン取得はMVPに含めない。
- eBay Browse APIがなくても全体が動くようにする。
- 売れた価格データがない候補を「高利益確定」と表示しない。
- データ不足は `NEEDS_RESEARCH` と判定する。
- 例外を握りつぶさない。
- SQLはAlembic migrationで管理する。
- 破壊的マイグレーションは自動実行しない。

## 使用技術

### 必須

- Python 3.11以上
- uv
- SQLAlchemy 2.x
- Alembic
- PyMySQL
- Pydantic 2.x
- pydantic-settings
- httpx
- tenacity
- RapidFuzz
- Typer
- pytest
- pytest-cov
- respx
- Ruff

### 任意

- Streamlit: MVPコア完成後
- pandas: Streamlit表示またはCSV分析に必要な場合だけ
- systemd timer: 本番定期実行
- GitHub Actions: lint/testのみ

## 実装スタイル

- APIクライアント、DB、計算、CLIを分離する。
- 型ヒントを付ける。
- Pydanticモデルで外部入力を検証する。
- SQLAlchemyモデルとAPIモデルを同一クラスにしない。
- 日時はUTCで保存し、表示時だけAsia/Tokyoへ変換する。
- ログは構造化し、APIキー・Authorizationヘッダーをマスクする。
- リトライは429、500、502、503、504など限定した一時エラーにだけ使う。
- 400、401、403、404を無条件リトライしない。
- APIごとのレート制限を設定可能にする。

## 推奨ディレクトリ

```text
.
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── alembic.ini
├── migrations/
├── src/
│   └── opportunity_finder/
│       ├── cli.py
│       ├── config.py
│       ├── logging_config.py
│       ├── db/
│       ├── domain/
│       ├── clients/
│       ├── services/
│       ├── imports/
│       └── exports/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── scripts/
└── deploy/systemd/
```

## 実装フェーズ

1. Foundation: 環境、設定、ログ、MySQL、Alembic
2. Offline MVP: CSV、利益計算、判定、CSV出力
3. Domestic APIs: Yahoo、楽天、正規化、照合
4. eBay: OAuth、Browse API、CSVフォールバック
5. Operations: CLI、systemd、バックアップ、CI
6. UI: Streamlit（任意）

## フェーズごとの完了報告

```text
実装したもの
変更ファイル
実行したコマンド
テスト結果
未解決事項
次に進む内容
```

## 禁止する近道

- モック値を本番データとして保存する
- `except Exception: pass`
- APIキーをハードコード
- 送料・手数料をコード直書き
- Product Researchの数値をAIで推測
- JAN不一致の商品を同一商品と断定
- 自動仕入れ・自動購入
- 自動出品
- AIだけで規制判定を承認

<!-- END: CLAUDE.md -->

---

<!-- BEGIN: docs/00_PROJECT_BRIEF.md -->
# 00. Project Brief

## 目的

日本国内で安く仕入れ、海外で高く売れる商品を探す作業を、感覚ではなくデータで行う。

本システムは、自動で商品を購入するものではない。候補を抽出し、仕入判断に必要な根拠を一画面または一CSVへ集約する。

## 解決する問題

商品価格差だけを見て仕入れると、国際送料と手数料で赤字になる。以下を一元化する。

- 国内価格
- 海外販売価格
- 販売数
- 競合数
- 送料
- eBay手数料
- 広告費
- 関税・通関費
- 返品リスク
- 商品重量
- 規制
- 原産国
- 継続仕入れ可否

## 対象利用者

- 日本在住の小規模越境EC事業者
- 初期資金3万〜10万円程度
- eBayを最初の販売先とする
- AI・自動化を活用したい
- 既存MySQLとVPSを利用したい

## MVP出力

- 国内最安仕入額
- 海外販売価格の根拠
- 推定国際送料
- 全費用
- 予想純利益
- 予想利益率
- 損益分岐販売価格
- 仕入資金効率
- 需要指標
- データ信頼度
- 判定
- 判定理由

## 判定種類

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

## 非目標

- 商品の自動購入
- eBayへの自動出品
- Product Researchへの自動ログイン
- CAPTCHA回避
- 食品、化粧品、医薬品、危険物の自動承認
- AIによる最終規制判定

## 成功指標

- CSV取込100件をエラーなく処理
- 利益計算が手計算と1円以内で一致
- 同じ入力なら同じ結果
- API障害時も過去データで再計算可能
- 1候補の計算根拠を追跡可能
- 上位10件だけProduct Researchで確認できる

<!-- END: docs/00_PROJECT_BRIEF.md -->

---

<!-- BEGIN: docs/01_ARCHITECTURE_AND_DATABASE.md -->
# 01. Architecture and MySQL Database

## 1. 基本方針

既存MySQLを唯一の永続DBとする。

```text
[CLI / Streamlit]
       ↓
[Application Services]
       ↓
[Domain: Profit / Score / Decision]
       ↓
[Repositories]
       ↓
[Existing MySQL]
```

外部APIはAdapter経由で利用する。

```text
Yahoo API ─────┐
Rakuten API ───┼→ Client Adapter → Normalizer → Repository
Browse API ────┤
CSV Import ────┘
```

## 2. 動作モード

### Mode A: Full API

- Yahoo API
- Rakuten API
- eBay Browse API
- Product Research CSV

### Mode B: No eBay API

- Yahoo API
- Rakuten API
- eBay active listing CSV
- Product Research CSV

### Mode C: Offline

- 国内商品CSV
- eBay CSV
- Product Research CSV
- 手動為替
- 手動送料表

すべてのテストはMode Cで実行可能にする。

## 3. コンポーネント

- `Config`: 環境変数と既定値
- `Clients`: 外部API。DBへ直接書かない
- `Normalizers`: 外部レスポンスを内部モデルへ変換
- `Matchers`: JAN、型番、商品名の照合
- `Repositories`: MySQL CRUD
- `Domain`: 利益、スコア、判定。外部I/Oなし
- `Services`: ユースケース実行
- `CLI`: 操作入口
- `Scheduler`: systemd timerからCLIを呼ぶ

## 4. MySQL採用理由

- 既存運用資産を再利用できる
- InnoDBトランザクション
- 価格履歴と販売履歴に適する
- 複合インデックスで十分な性能
- raw APIをJSON列へ保存可能
- 新しいDBの監視・バックアップが不要

## 5. 前提

- MySQL 8.0以上
- InnoDB
- `utf8mb4`
- UTC保存
- 専用DB: `ebay_opportunity`
- schema変更はAlembicのみ

確認コマンド:

```bash
mysql --version
mysql -Nse "SELECT VERSION();"
```

MariaDBの場合はMySQLと同一扱いにせず、互換性確認を行う。

## 6. DB作成例

```sql
CREATE DATABASE IF NOT EXISTS ebay_opportunity
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'ebay_finder'@'localhost'
  IDENTIFIED BY 'CHANGE_ME';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON ebay_opportunity.* TO 'ebay_finder'@'localhost';
```

本番パスワードはシェル履歴へ残さない。

## 7. データ型ルール

- 金額: `DECIMAL(18,4)`
- 率: `DECIMAL(10,6)`
- 重量: `INT UNSIGNED`
- 日時: `DATETIME(6)`
- Boolean: `BOOLEAN`
- raw API: `JSON`
- status: `VARCHAR(32)`

`ENUM`はmigrationの柔軟性が下がるため原則使わない。

## 8. テーブル概要

| テーブル | 用途 |
|---|---|
| `products` | 商品マスタ |
| `supplier_items` | 国内仕入先の商品識別 |
| `supplier_price_snapshots` | 国内価格履歴 |
| `market_queries` | eBay検索条件 |
| `ebay_listings` | eBay出品識別 |
| `ebay_listing_snapshots` | eBay現在価格履歴 |
| `market_research_metrics` | Product Research販売済み指標 |
| `exchange_rates` | 為替履歴 |
| `shipping_rates` | 送料表 |
| `fee_rules` | 手数料・引当ルール |
| `opportunity_snapshots` | 計算結果履歴 |
| `scan_runs` | バッチ実行履歴 |
| `import_batches` | CSV取込履歴 |
| `audit_logs` | 手動変更監査 |

## 9. 主要DDL

### products

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    jan_code VARCHAR(14) NULL,
    internal_sku VARCHAR(64) NULL,
    normalized_name VARCHAR(512) NOT NULL,
    original_name VARCHAR(512) NOT NULL,
    brand VARCHAR(255) NULL,
    model_number VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    origin_country CHAR(2) NULL,
    unit_count INT UNSIGNED NOT NULL DEFAULT 1,
    weight_g INT UNSIGNED NULL,
    package_length_mm INT UNSIGNED NULL,
    package_width_mm INT UNSIGNED NULL,
    package_height_mm INT UNSIGNED NULL,
    repeatable_supply BOOLEAN NOT NULL DEFAULT FALSE,
    compliance_status VARCHAR(32) NOT NULL DEFAULT 'NEEDS_REVIEW',
    compliance_flags JSON NULL,
    notes TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_products_jan (jan_code),
    UNIQUE KEY uq_products_internal_sku (internal_sku),
    KEY ix_products_brand_model (brand, model_number),
    KEY ix_products_status (compliance_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### supplier_items / supplier_price_snapshots

```sql
CREATE TABLE supplier_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NOT NULL,
    source VARCHAR(32) NOT NULL,
    external_item_id VARCHAR(255) NOT NULL,
    shop_name VARCHAR(255) NULL,
    title VARCHAR(512) NOT NULL,
    item_url TEXT NULL,
    jan_code VARCHAR(14) NULL,
    brand VARCHAR(255) NULL,
    model_number VARCHAR(255) NULL,
    match_method VARCHAR(32) NOT NULL,
    match_confidence DECIMAL(10,6) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    raw_payload JSON NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_supplier_items_product
      FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE KEY uq_supplier_external (source, external_item_id),
    KEY ix_supplier_product_source (product_id, source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE supplier_price_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    supplier_item_id BIGINT UNSIGNED NOT NULL,
    item_price_jpy DECIMAL(18,4) NOT NULL,
    domestic_shipping_jpy DECIMAL(18,4) NOT NULL DEFAULT 0,
    points_value_jpy DECIMAL(18,4) NOT NULL DEFAULT 0,
    coupon_value_jpy DECIMAL(18,4) NOT NULL DEFAULT 0,
    available BOOLEAN NOT NULL,
    effective_cost_jpy DECIMAL(18,4) NOT NULL,
    captured_at DATETIME(6) NOT NULL,
    raw_payload JSON NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_supplier_price_item
      FOREIGN KEY (supplier_item_id) REFERENCES supplier_items(id),
    UNIQUE KEY uq_supplier_price_capture (supplier_item_id, captured_at),
    KEY ix_supplier_price_latest (supplier_item_id, captured_at),
    KEY ix_supplier_effective_cost (effective_cost_jpy)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### market_queries / market_research_metrics

```sql
CREATE TABLE market_queries (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NULL,
    marketplace VARCHAR(32) NOT NULL DEFAULT 'EBAY_US',
    query_text VARCHAR(512) NOT NULL,
    category_id VARCHAR(64) NULL,
    condition_filter VARCHAR(64) NULL,
    query_type VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_market_query_product
      FOREIGN KEY (product_id) REFERENCES products(id),
    KEY ix_market_query_product (product_id),
    KEY ix_market_query_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE market_research_metrics (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    query_id BIGINT UNSIGNED NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'PRODUCT_RESEARCH',
    period_days INT UNSIGNED NOT NULL,
    sold_count INT UNSIGNED NULL,
    active_count INT UNSIGNED NULL,
    seller_count INT UNSIGNED NULL,
    median_sold_price DECIMAL(18,4) NULL,
    average_sold_price DECIMAL(18,4) NULL,
    minimum_sold_price DECIMAL(18,4) NULL,
    maximum_sold_price DECIMAL(18,4) NULL,
    average_shipping DECIMAL(18,4) NULL,
    currency CHAR(3) NOT NULL,
    sell_through_rate DECIMAL(10,6) NULL,
    researched_at DATETIME(6) NOT NULL,
    valid_until DATETIME(6) NULL,
    notes TEXT NULL,
    import_batch_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_research_query
      FOREIGN KEY (query_id) REFERENCES market_queries(id),
    KEY ix_research_latest (query_id, researched_at),
    KEY ix_research_sellthrough (sell_through_rate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### opportunity_snapshots

```sql
CREATE TABLE opportunity_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NOT NULL,
    query_id BIGINT UNSIGNED NOT NULL,
    scenario VARCHAR(32) NOT NULL,
    source_cost_jpy DECIMAL(18,4) NOT NULL,
    buyer_total_market_currency DECIMAL(18,4) NOT NULL,
    market_currency CHAR(3) NOT NULL,
    exchange_rate DECIMAL(18,8) NOT NULL,
    revenue_jpy DECIMAL(18,4) NOT NULL,
    marketplace_fees_jpy DECIMAL(18,4) NOT NULL,
    advertising_reserve_jpy DECIMAL(18,4) NOT NULL,
    return_reserve_jpy DECIMAL(18,4) NOT NULL,
    duty_processing_jpy DECIMAL(18,4) NOT NULL,
    international_shipping_jpy DECIMAL(18,4) NOT NULL,
    packaging_jpy DECIMAL(18,4) NOT NULL,
    other_costs_jpy DECIMAL(18,4) NOT NULL,
    total_cost_jpy DECIMAL(18,4) NOT NULL,
    net_profit_jpy DECIMAL(18,4) NOT NULL,
    net_margin DECIMAL(10,6) NOT NULL,
    break_even_buyer_total DECIMAL(18,4) NOT NULL,
    capital_required_jpy DECIMAL(18,4) NOT NULL,
    capital_efficiency DECIMAL(10,6) NOT NULL,
    opportunity_score DECIMAL(10,4) NOT NULL,
    data_confidence DECIMAL(10,4) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    reason_codes JSON NOT NULL,
    input_snapshot JSON NOT NULL,
    calculated_at DATETIME(6) NOT NULL,
    calculator_version VARCHAR(64) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_opportunity_product
      FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT fk_opportunity_query
      FOREIGN KEY (query_id) REFERENCES market_queries(id),
    KEY ix_opportunity_rank (scenario, decision, opportunity_score),
    KEY ix_opportunity_profit (net_profit_jpy),
    KEY ix_opportunity_product_time (product_id, calculated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

他のテーブルも同じ原則でAlembicに実装する。

## 10. インデックス原則

- 最新取得: `(entity_id, captured_at)`
- ランキング: `(scenario, decision, opportunity_score)`
- 商品照合: JAN、ブランド＋型番
- JSON内の頻出値は通常列へ昇格
- 不要なインデックスを大量に作らない

## 11. Migration方針

- `0001_initial_schema`
- `0002_seed_default_rules`
- 以降は1変更1migration
- 本番適用前に `mysqldump --single-transaction`
- カラム削除は2段階
- 破壊的変更は自動実行しない

## 12. バックアップ

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  ebay_opportunity \
  | gzip > "backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

<!-- END: docs/01_ARCHITECTURE_AND_DATABASE.md -->

---

<!-- BEGIN: docs/02_DATA_APIS_AND_OSS.md -->
# 02. Data Sources, APIs and OSS

## 1. 取得手段の優先順位

1. 公式API
2. 公式CSV・手動エクスポート
3. 手動入力
4. 利用規約上許可された低頻度ブラウザ補助
5. 非公式スクレイピングはMVPで不採用

## 2. eBay

### Browse API

用途:

- 現在出品の検索
- GTIN、キーワード、カテゴリ検索
- 商品価格
- 送料
- condition
- active competitionの補助

制約:

- 本番利用には申請・承認が必要
- Application access tokenをClient Credentialsで取得
- 主に現在出品であり、販売済み履歴の代替ではない
- `total`だけを厳密な競合数として盲信しない
- ページングは`next`を優先
- 検索結果はタイトル完全一致だけではない

### Marketplace Insights API

- 制限公開
- 新規利用者に開放されていない
- MVPの前提にしない

### Product Research

手動で以下をCSVへ記録する。

- query
- marketplace
- period_days
- sold_count
- active_count
- median_sold_price
- average_sold_price
- average_shipping
- sell_through_rate
- seller_count
- researched_at
- notes

### 旧API

Finding APIとShopping APIは廃止済み。新規コードで使用しない。

### eBay APIが使えない場合

```text
Product Research CSV
+ eBay現在出品の手動CSV
+ 国内API
+ 利益計算
```

## 3. Yahoo!ショッピングAPI

商品検索 v3を使う。

検索順:

1. `jan_code`
2. `query`

保存:

- 商品コード
- 商品名
- 価格
- 送料
- ストア
- URL
- JAN
- 画像URL
- raw JSON

## 4. 楽天API

### Product Search

- JANから製品情報
- 製品名
- ブランド
- 型番

### Ichiba Item Search 2026-07-01

- 製品名・型番から販売中商品
- 価格
- 在庫
- ストア
- URL
- Application ID + Access Key

## 5. 手動CSV

### products.csv

```csv
original_name,jan_code,brand,model_number,category,origin_country,weight_g,repeatable_supply,notes
Kokuyo Campus Notebook,4901480xxxxxx,KOKUYO,NO-3AN,stationery,JP,180,true,
```

### product_research.csv

```csv
query_text,marketplace,period_days,sold_count,active_count,seller_count,median_sold_price,average_sold_price,average_shipping,currency,sell_through_rate,researched_at,notes
Kokuyo model number,EBAY_US,90,14,42,11,39.99,41.20,6.50,USD,0.25,2026-08-06T00:00:00Z,
```

## 6. データ優先順位

### 国内価格

1. 実仕入価格
2. 在庫ありの公式API価格
3. 手動入力
4. 参考価格

### 海外販売価格

1. Product Research sold median
2. Product Research sold average
3. active listing median
4. active listing minimum
5. 推測値は使用禁止

### 重量

1. 実測梱包後重量
2. メーカー公称＋梱包加算
3. 商品ページ
4. 推定値

## 7. API共通実装

- `httpx.Client`
- connect/read timeout
- 429と5xxの限定リトライ
- exponential backoff + jitter
- request ID保存
- 認証情報マスク
- raw payload保存
- response schema検証
- API仕様変更を検知するcontract test

## 8. 採用OSS

| 用途 | OSS | 理由 |
|---|---|---|
| パッケージ管理 | `astral-sh/uv` | lockfile、Python管理、CI連携 |
| ORM | `sqlalchemy/sqlalchemy` | MySQL対応、成熟 |
| migration | `sqlalchemy/alembic` | SQLAlchemy標準 |
| MySQL driver | `PyMySQL/PyMySQL` | Pure Python、軽量 |
| HTTP | `encode/httpx` | timeout、pool、sync/async |
| 入力検証 | `pydantic/pydantic` | API/CSV検証 |
| 設定 | `pydantic/pydantic-settings` | env型検証 |
| リトライ | `jd/tenacity` | 上限付きbackoff |
| 類似文字列 | `rapidfuzz/RapidFuzz` | 商品名照合 |
| CLI | `fastapi/typer` | 型ヒント、subcommand |
| 表示 | `Textualize/rich` | 表、進捗、エラー |
| テスト | `pytest-dev/pytest` | fixture、標準的 |
| lint/format | `astral-sh/ruff` | ツール数削減 |
| UI任意 | `streamlit/streamlit` | Pythonのみで管理画面 |

## 9. eBay関連GitHubの判断

### `eBay/ebay-oauth-python-client`

不採用。公式だがPython 2.7向け。OAuthフローの参考だけにし、HTTPXで薄く直接実装する。

### `AverHLV/browseapi`

不採用。2020年にarchive。最新API仕様への追従を期待できない。

### `eBay/ebay-items-react-widget`

Browse API例として参考のみ。React UIはMVP対象外。

## 10. 採用しない大型OSS

- Airflow / Dagster / Prefect: 日次単一バッチには過剰
- PostgreSQL / DuckDB: 既存MySQLで足りる
- Redis / Celery: 並列ジョブ不要
- n8n: 通知用に後から任意追加
- Selenium / Playwright: Product Research自動取得には不採用

## 11. 最小依存案

```toml
[project]
dependencies = [
  "sqlalchemy>=2.0,<2.1",
  "alembic>=1.17,<2",
  "pymysql>=1.1,<2",
  "httpx>=0.28,<1",
  "pydantic>=2.12,<3",
  "pydantic-settings>=2.10,<3",
  "tenacity>=9,<10",
  "rapidfuzz>=3,<4",
  "typer>=0.24,<1",
  "rich>=14,<15",
]
```

実装時に互換性を確認し、`uv.lock`で固定する。

<!-- END: docs/02_DATA_APIS_AND_OSS.md -->

---

<!-- BEGIN: docs/03_PROFIT_AND_SCORING.md -->
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

<!-- END: docs/03_PROFIT_AND_SCORING.md -->

---

<!-- BEGIN: docs/04_IMPLEMENTATION_AND_TESTS.md -->
# 04. 実装計画・CLI・テスト・受入条件

## 1. 実装方針

一度に全機能を作らない。最初に「CSVを入れるとMySQLへ保存し、利益を計算し、候補ランキングを出す」オフラインMVPを完成させる。

API連携、画面、AIはその後に追加する。

## 2. 推奨リポジトリ構成

```text
japan-ebay-opportunity-finder/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── alembic.ini
├── config/
│   ├── settings.example.yaml
│   ├── candidate_rules.yaml
│   ├── risk_rules.yaml
│   └── fee_profiles.example.yaml
├── migrations/
│   ├── env.py
│   └── versions/
├── src/
│   └── opportunity_finder/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── logging.py
│       ├── db/
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models.py
│       │   └── repositories/
│       ├── domain/
│       │   ├── money.py
│       │   ├── product.py
│       │   ├── market.py
│       │   ├── profit.py
│       │   ├── scoring.py
│       │   ├── decisions.py
│       │   └── compliance.py
│       ├── clients/
│       │   ├── base.py
│       │   ├── ebay_browse.py
│       │   ├── yahoo_shopping.py
│       │   ├── rakuten_ichiba.py
│       │   ├── rakuten_product.py
│       │   └── exchange_rate.py
│       ├── services/
│       │   ├── import_service.py
│       │   ├── matching_service.py
│       │   ├── market_service.py
│       │   ├── opportunity_service.py
│       │   └── reporting_service.py
│       ├── importers/
│       │   ├── products_csv.py
│       │   ├── product_research_csv.py
│       │   ├── fees_csv.py
│       │   └── shipping_csv.py
│       └── exporters/
│           ├── opportunities_csv.py
│           └── audit_jsonl.py
├── dashboard/
│   └── app.py
├── scripts/
│   ├── daily_run.sh
│   ├── backup_mysql.sh
│   └── restore_mysql_example.sh
├── deploy/
│   └── systemd/
│       ├── opportunity-finder.service
│       └── opportunity-finder.timer
├── data/
│   ├── samples/
│   └── imports/.gitkeep
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
└── .github/
    └── workflows/
        └── ci.yml
```

## 3. 実装フェーズ

### Phase 0: プロジェクト基盤

完了条件:

- `uv` で依存関係を管理
- `ruff check` と `ruff format --check` が通る
- `pytest` が実行できる
- `.env` からMySQL接続設定を読む
- 構造化ログを出せる
- `finder --help` が動く

### Phase 1: オフラインMVP

機能:

1. MySQLマイグレーション
2. 国内商品CSV取込
3. Product Research CSV取込
4. 送料表・手数料表・為替の取込
5. 利益計算
6. 3シナリオ計算
7. 候補判定
8. CSVランキング出力
9. 監査ログ

この段階では外部APIなしでも完動させる。

### Phase 2: 国内API

順番:

1. Yahoo!ショッピング商品検索
2. 楽天市場商品検索
3. 楽天製品検索
4. JAN・型番・名称の統合
5. 最安値ではなく送料込み実質価格を保存

必須:

- APIレスポンスを生JSONとして保存可能にする
- タイムアウト、429、5xxへリトライ
- 失敗しても既存データからランキングを継続
- 利用規約に反する取得をしない

### Phase 3: eBay Browse API

前提:

- Production accessが承認されている場合のみ有効化
- 未承認、403、権限不足なら自動的にCSVモードへ戻る

機能:

- OAuth Application Token取得
- キーワード検索
- GTIN検索
- ページネーション
- 価格・送料・状態・seller country等の保存
- 外れ値除外後の中央値
- 同一商品信頼度判定

禁止:

- 廃止済みFinding APIを利用しない
- Marketplace Insights APIが使えると仮定しない
- HTMLスクレイピングをAPIの代替にしない

### Phase 4: 定期実行と運用

- `systemd timer` で日次実行
- 既存MySQLへ保存
- エラー時は終了コードを非0にする
- ログローテーション
- バックアップ
- CSV出力
- Slack Webhookは任意

### Phase 5: Streamlit画面

MVP完了後の任意機能。

画面:

- 候補ランキング
- 商品詳細
- コスト内訳
- 3シナリオ比較
- 手動Product Research入力
- 規制承認・却下
- 仕入れ済みフラグ
- CSVダウンロード

Streamlitを本番の唯一の管理方法にしない。CLIとDBだけでも運用可能にする。

### Phase 6: 実績利益と改善

- 注文実績取込
- 予測利益と実績利益の比較
- 送料誤差
- 関税誤差
- 返品損失
- SKU別補充判定

## 4. CLI仕様

CLI名は `finder` とする。

### DB

```bash
finder db check
finder db upgrade
finder db current
```

### インポート

```bash
finder import products data/imports/products.csv
finder import product-research data/imports/product_research.csv
finder import shipping data/imports/shipping_rates.csv
finder import fees data/imports/fee_profiles.csv
finder import exchange data/imports/exchange_rates.csv
```

### データ取得

```bash
finder fetch domestic --source yahoo --limit 100
finder fetch domestic --source rakuten --limit 100
finder fetch ebay --query-id 123
finder fetch all --stale-only
```

### 計算

```bash
finder calculate opportunities
finder calculate opportunity --product-id 123
finder calculate break-even --product-id 123
```

### レポート

```bash
finder report top --limit 30
finder report top --decision BUY_TEST_1 --format table
finder export opportunities output/opportunities.csv
finder export audit output/audit.jsonl
```

### 日次処理

```bash
finder daily --stale-only --export-dir output/daily
```

`daily` の処理順:

1. DB接続確認
2. 設定検証
3. 為替更新
4. 古い国内価格のみ更新
5. eBay APIが利用可能なら更新
6. Product Research CSVの新規ファイル取込
7. 機会スナップショット計算
8. 上位候補CSV出力
9. 実行サマリー出力
10. 失敗件数が閾値超過なら非0終了

## 5. CSV仕様

### 5.1 products.csv

```csv
external_key,jan,title,brand,model_number,condition,source_cost_jpy,source_shipping_jpy,weight_g,packed_weight_g,origin_country,supplier_name,supplier_url,checked_at
local-001,4900000000000,商品名,Brand,MODEL-1,new,1980,0,300,380,JP,Shop,https://example.invalid,2026-08-06T09:00:00+09:00
```

### 5.2 product_research.csv

```csv
external_key,search_query,marketplace,condition,lookback_days,sold_count,active_count,median_sold_price_usd,average_sold_price_usd,median_buyer_shipping_usd,sell_through_rate,checked_at,notes
local-001,Brand MODEL-1,EBAY_US,new,90,12,30,69.99,68.50,0,0.2857,2026-08-06T09:30:00+09:00,Product Research manual export
```

### 5.3 shipping_rates.csv

```csv
profile_code,destination_country,min_weight_g,max_weight_g,service_name,shipping_jpy,tracking,included_insurance_jpy,effective_from,effective_to
US_DDP_001,US,0,500,SpeedPAK Economy,1800,true,0,2026-08-01,
```

### 5.4 fee_profiles.csv

```csv
profile_code,marketplace,category_code,variable_fee_rate,international_fee_rate,fixed_fee_currency,fixed_fee_amount,ad_rate,return_reserve_rate,effective_from,effective_to
EBAY_US_DEFAULT,EBAY_US,,0.136,0.0135,USD,0.40,0.03,0.03,2026-08-01,
```

上記はサンプル値である。現行規約を確認し、実際の値を入力すること。

## 6. Pydanticモデル

最低限必要なモデル:

- `Money`
- `ProductInput`
- `SupplierOffer`
- `MarketResearchInput`
- `FeeProfile`
- `ShippingQuote`
- `ProfitInput`
- `ProfitScenarioResult`
- `OpportunityResult`
- `ComplianceDecision`

全入力値を境界で検証する。

例:

- 金額が負数でない
- 重量が正数
- Sell-throughが0〜1
- 国コードはISO形式
- 日付にタイムゾーンがある
- JANは数字のみ、桁数検証
- URLスキーム検証

## 7. テスト計画

### 7.1 Unit tests

#### Money

- Decimal変換
- 通貨丸め
- 円の端数処理
- float入力拒否または安全変換

#### Profit

- 基本利益
- 固定手数料
- 広告なし
- 関税なし
- 赤字
- 0売上の除算回避
- Conservativeシナリオ
- 損益分岐価格

#### Scoring

- 上限・下限
- 売上0件
- 高利益低需要
- 低利益高需要
- リスク控除

#### Decisions

- BLOCKEDが最優先
- 不足データ
- 古いデータ
- BUY_TEST_1/2
- REPLENISH

#### Matching

- JAN完全一致
- 型番一致
- セット数違い
- 新品・中古違い
- RapidFuzz類似度
- ブランド誤一致

### 7.2 CSV tests

- 正常ファイル
- 必須列欠落
- 重複行
- 文字コード
- 不正な日付
- 不正な数値
- Excel数式インジェクション対策
- 途中失敗時のトランザクション

### 7.3 API contract tests

HTTPXのMockTransportまたは `respx` を使用して以下を確認する。

- 200
- 204
- 400
- 401
- 403
- 404
- 429
- 500/502/503
- タイムアウト
- 不正JSON
- ページネーション
- レート制限ヘッダー
- eBay権限不足時のCSVフォールバック

### 7.4 MySQL integration tests

テスト専用MySQL DBを使う。

- Alembic upgrade/downgrade
- 一意制約
- 外部キー
- トランザクションrollback
- upsert
- 同時更新
- generated columnを使う場合の動作
- EXPLAINで主要クエリのインデックス利用確認

SQLiteでMySQL統合テストを代用しない。

### 7.5 End-to-end test

サンプルCSVから以下を一回で検証する。

```bash
finder db upgrade
finder import products data/samples/products.csv
finder import product-research data/samples/product_research.csv
finder import shipping data/samples/shipping_rates.csv
finder import fees data/samples/fee_profiles.csv
finder calculate opportunities
finder report top --limit 10
finder export opportunities /tmp/opportunities.csv
```

期待値:

- エラーなく完了
- DBへスナップショット保存
- 上位候補が所定順
- コスト内訳合計が一致
- CSVに必要列が存在
- BLOCKED商品が購入候補に出ない

## 8. 品質ゲート

CIで以下を必須とする。

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

推奨:

- ドメインロジックのカバレッジ90%以上
- 全体80%以上
- 型チェックは `pyright` を追加してもよい
- secret scanを有効化
- 依存関係更新は人間承認

## 9. 受入条件

MVPは以下をすべて満たしたら完成とする。

1. 既存MySQL以外のDBを必要としない
2. 外部APIなしでサンプルCSVから動く
3. 利益の全費目が説明可能
4. 3シナリオを計算する
5. 損益分岐価格を出す
6. 候補ステータスを出す
7. スコア根拠を保存する
8. Product Research手入力CSVを扱える
9. eBay API権限不足でも停止しない
10. 監査ログが残る
11. 再実行して重複しない
12. テストが通る
13. READMEに初期設定と運用手順がある
14. 本番シークレットをGitへ入れない
15. 一つのコマンドで日次更新できる

## 10. Claude Codeへの実装上の注意

- まず既存リポジトリとMySQL接続方法を調査する
- 既存コードを破壊しない
- 大規模変更前に小さなコミット単位へ分ける
- 仕様にない外部サービスを勝手に追加しない
- 新しいDB、Redis、Docker常駐サービスを勝手に増やさない
- APIが使えない場合にスクレイピングへ逃げない
- 手数料・送料・基準値をハードコードしない
- 実装後は必ずテストとサンプル実行を行う

<!-- END: docs/04_IMPLEMENTATION_AND_TESTS.md -->

---

<!-- BEGIN: docs/05_OPERATIONS_AND_SECURITY.md -->
# 05. 運用・systemd・バックアップ・セキュリティ

## 1. 運用方針

- 既存VPSまたは既存Ubuntu環境を利用する
- 既存MySQLサーバー内に専用データベースと専用ユーザーを作る
- 日次処理は `systemd timer` を第一候補とする
- GitHub ActionsはCIに使い、本番の日次データ取得はVPSで実行する
- 追加のDB、Redis、メッセージキューはMVPでは導入しない
- 物理商品の仕入れ判断は人間承認を残す

## 2. MySQL前提

推奨:

- MySQL 8.0以上
- `utf8mb4`
- タイムゾーンはDB保存時UTC、表示時Asia/Tokyo
- InnoDB
- 専用DB名: `ebay_opportunity`
- 専用ユーザーは対象DBだけに権限を付ける

例:

```sql
CREATE DATABASE ebay_opportunity
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'opportunity_app'@'localhost'
  IDENTIFIED BY 'REPLACE_WITH_STRONG_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON ebay_opportunity.*
TO 'opportunity_app'@'localhost';

FLUSH PRIVILEGES;
```

本番ではマイグレーション用ユーザーと通常実行ユーザーを分ける方が安全である。

既存環境がMariaDBまたはMySQL 5.7の場合、JSON式インデックスや一部DDLが異なる可能性があるため、実装前にバージョンを確認する。

```bash
mysql --version
mysql -Nse 'SELECT VERSION();'
```

## 3. `.env.example`

```dotenv
APP_ENV=development
APP_TIMEZONE=Asia/Tokyo
LOG_LEVEL=INFO

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=ebay_opportunity
MYSQL_USER=opportunity_app
MYSQL_PASSWORD=change-me
MYSQL_POOL_SIZE=5
MYSQL_MAX_OVERFLOW=5

EBAY_ENABLED=false
EBAY_ENVIRONMENT=production
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
EBAY_MARKETPLACE_ID=EBAY_US

YAHOO_SHOPPING_ENABLED=false
YAHOO_CLIENT_ID=

RAKUTEN_ENABLED=false
RAKUTEN_APPLICATION_ID=
RAKUTEN_ACCESS_KEY=
RAKUTEN_AFFILIATE_ID=

EXCHANGE_RATE_SOURCE=manual
DEFAULT_USD_JPY=157.0

IMPORT_DIR=/opt/opportunity-finder/data/imports
EXPORT_DIR=/opt/opportunity-finder/output
RAW_RESPONSE_DIR=/opt/opportunity-finder/data/raw

SLACK_WEBHOOK_URL=
```

`.env` はGitへコミットしない。

## 4. systemd service

`deploy/systemd/opportunity-finder.service`:

```ini
[Unit]
Description=Japan eBay Opportunity Finder Daily Job
After=network-online.target mysql.service
Wants=network-online.target

[Service]
Type=oneshot
User=opportunity
Group=opportunity
WorkingDirectory=/opt/opportunity-finder
EnvironmentFile=/etc/opportunity-finder/opportunity-finder.env
ExecStart=/opt/opportunity-finder/.venv/bin/finder daily --stale-only --export-dir /opt/opportunity-finder/output/daily
TimeoutStartSec=1800
Nice=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/opportunity-finder/data /opt/opportunity-finder/output /opt/opportunity-finder/logs

[Install]
WantedBy=multi-user.target
```

環境に応じてMySQLのunit名やパスを調整する。

## 5. systemd timer

`deploy/systemd/opportunity-finder.timer`:

```ini
[Unit]
Description=Run Opportunity Finder every day

[Timer]
OnCalendar=*-*-* 06:30:00 Asia/Tokyo
Persistent=true
RandomizedDelaySec=300
Unit=opportunity-finder.service

[Install]
WantedBy=timers.target
```

有効化:

```bash
sudo cp deploy/systemd/opportunity-finder.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opportunity-finder.timer
systemctl list-timers --all | grep opportunity-finder
```

手動試験:

```bash
sudo systemctl start opportunity-finder.service
sudo systemctl status opportunity-finder.service
journalctl -u opportunity-finder.service -n 200 --no-pager
```

## 6. ログ

必須フィールド:

- timestamp
- level
- run_id
- command
- source
- product_id/query_id
- elapsed_ms
- status
- error_type
- retry_count
- rows_read
- rows_written

APIトークン、Cookie、顧客個人情報、MySQLパスワードを出力しない。

日次処理ごとに `run_id` を生成し、DBの `job_runs` とログを結びつける。

## 7. 冪等性

同じCSVや同じAPIレスポンスを再処理しても重複しないようにする。

推奨キー:

- 商品: `source + external_key` または `jan + model_number`
- 国内価格: `supplier_item_id + checked_at`
- 市場データ: `market_query_id + period_start + period_end + checked_at`
- 機会計算: `product_id + scenario + calculated_at_bucket`
- CSV取込: SHA-256

取込ファイルのハッシュと処理結果を記録する。

## 8. MySQLバックアップ

日次または週次で専用DBをバックアップする。

`scripts/backup_mysql.sh` の例:

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/opportunity-finder}"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="${BACKUP_DIR}/ebay_opportunity_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --set-gtid-purged=OFF \
  "${MYSQL_DATABASE}" | gzip -9 > "$FILE"

find "$BACKUP_DIR" -type f -name '*.sql.gz' -mtime +30 -delete
printf 'created: %s\n' "$FILE"
```

パスワードをコマンドライン引数へ直接書かず、`mysql_config_editor`、保護された設定ファイル、またはsystemd credentialsを使用する。

復元試験を定期的に行う。バックアップを作るだけでは不十分である。

## 9. GitHub Actions

CIだけを基本とする。

`.github/workflows/ci.yml` 例:

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      mysql:
        image: mysql:8.4
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: finder_test
          MYSQL_USER: finder
          MYSQL_PASSWORD: finder
        ports:
          - 3306:3306
        options: >-
          --health-cmd="mysqladmin ping -h 127.0.0.1 -uroot -proot"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=10

    env:
      MYSQL_HOST: 127.0.0.1
      MYSQL_PORT: 3306
      MYSQL_DATABASE: finder_test
      MYSQL_USER: finder
      MYSQL_PASSWORD: finder

    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run alembic upgrade head
      - run: uv run pytest -q
```

外部APIの本番キーを通常CIへ入れない。API contract testsはモックで行う。

## 10. API障害時の動作

| 障害 | 動作 |
|---|---|
| Yahoo/Rakuten timeout | リトライ後、既存価格をSTABLE/STALEとして使用 |
| 429 | Retry-Afterに従い、処理量を減らす |
| eBay 401 | トークン再取得を1回だけ試す |
| eBay 403/権限不足 | eBay APIを当該runで無効化しCSVモードへ |
| eBay 5xx | リトライ後に既存市場データを利用 |
| 為替API失敗 | 最終取得値を使用し、鮮度警告 |
| MySQL接続失敗 | 書き込みをせず非0終了 |
| CSV不正 | ファイル単位で隔離し、他ファイルを継続 |

古いデータを使った場合は、候補ランキングへ `STALE_DATA` を明示する。

## 11. セキュリティ

### 必須

- シークレットをGitへ入れない
- MySQLをインターネットへ公開しない
- アプリはrootで実行しない
- DBユーザーを最小権限にする
- APIキーをログへ出さない
- 外部URLへアクセスする処理はSSRF対策をする
- CSV出力時に `=`, `+`, `-`, `@` で始まるセルを無害化する
- HTMLを表示する場合はエスケープする
- APIレスポンスを信用せずPydanticで検証する
- 依存パッケージを定期監査する

### 商品データ上のリスク

以下は自動購入候補から除外する初期ルールにする。

- 食品、飲料
- 化粧品、液体
- 医薬品、サプリメント
- スプレー、可燃物
- 電池単体
- 強磁性品
- ナイフ等の刃物
- 植物、種子
- 高額ブランド品で真贋資料がないもの
- リコール、安全警告対象
- 原産国不明で配送条件に影響するもの

爪切り、工具、子供向け製品、食品接触製品などは一律許可せず、国・配送方法・プラットフォームの確認を要求する。

## 12. スクレイピング方針

- 公式APIを第一選択にする
- robots.txtだけで合法・規約適合と判断しない
- 利用規約、レート制限、認証条件を確認する
- CAPTCHA回避を実装しない
- ログイン状態やCookieを盗用しない
- eBay Product Researchの自動取得は、明示的に許可される手段が確認できるまで実装しない
- ブラウザ自動化は管理画面の補助操作に限定し、主要データ取得の基盤にしない

## 13. AI利用方針

AIを使ってよい:

- 英語検索語候補
- 商品名正規化候補
- ブランド・型番抽出候補
- 商品説明の下書き
- 規制確認項目のチェックリスト
- 異常値の説明

AIへ任せない:

- 最終利益計算
- 最終規制判定
- 真贋判定
- HSコードの最終確定
- 仕入れ自動発注
- 返金、紛争対応

AI出力は入力データ、モデル、プロンプト、日時を保存できる設計にする。

## 14. 監視項目

- 日次処理成功/失敗
- API別成功率
- 429率
- 取得件数
- データ鮮度
- 利益候補件数
- DB容量
- バックアップ成功
- 利益予測誤差
- 重複率
- マッチング信頼度分布

最初はログと日次サマリーで十分。Prometheus等は問題が発生してから追加する。

<!-- END: docs/05_OPERATIONS_AND_SECURITY.md -->

---

<!-- BEGIN: docs/06_CLAUDE_CODE_EXECUTION_PROMPT.md -->
# 06. Claude Code実行用プロンプト

以下をClaude Codeへ渡す。リポジトリに本資料一式を置き、Claude Codeには最初に `CLAUDE.md` と `docs/` 全体を読ませる。

---

## コピペ用プロンプト

あなたは既存MySQLを利用するPythonプロジェクトの実装担当です。

このリポジトリ内の以下を、実装前にすべて読んでください。

1. `CLAUDE.md`
2. `README.md`
3. `docs/00_PROJECT_BRIEF.md`
4. `docs/01_ARCHITECTURE_AND_DATABASE.md`
5. `docs/02_DATA_APIS_AND_OSS.md`
6. `docs/03_PROFIT_AND_SCORING.md`
7. `docs/04_IMPLEMENTATION_AND_TESTS.md`
8. `docs/05_OPERATIONS_AND_SECURITY.md`

目的は、日本国内の仕入価格とeBay等の海外市場データを比較し、送料、手数料、関税・処理費、広告、返品引当まで差し引いた予想純利益を計算して、高利益の仕入れ候補をランキングするツールを作ることです。

### 絶対条件

- 新しいDBを導入しないでください
- 既存MySQLを使ってください
- PostgreSQL、DuckDB、Supabase、Redisを追加しないでください
- 外部APIなしでもCSVだけでMVPが完動するようにしてください
- eBay Finding APIとShopping APIを使わないでください
- Marketplace Insights APIが利用できると仮定しないでください
- eBay Browse APIは権限がある場合だけ使い、403や未承認時はCSVモードへフォールバックしてください
- CAPTCHA回避や非公式ログインスクレイピングを実装しないでください
- 金額計算は `Decimal` を使い、floatへ依存しないでください
- 手数料、送料、為替、判定基準をコードへ直書きしないでください
- 規制、真贋、危険物の最終判断をAIへ任せないでください
- 実装しただけで終わらず、テストとサンプル実行まで行ってください

### 最初に行うこと

1. リポジトリ全体を調査してください
2. 既存のPython、MySQL、systemd、CI構成を確認してください
3. `mysql --version` または設定からMySQL/MariaDBの種類とバージョンを確認してください
4. 既存コードを再利用できる箇所を一覧化してください
5. 仕様と既存構成の差分を整理してください
6. 実装計画を小さなフェーズに分けてください
7. 不明点があっても、仕様から合理的に決められるものは決めて進めてください
8. 破壊的変更が必要な場合のみ明示してください

### 最初に作る範囲

Phase 0とPhase 1を先に完成させてください。

#### Phase 0

- `pyproject.toml`
- uv依存管理
- Ruff
- pytest
- Pydantic Settings
- SQLAlchemy 2.x
- Alembic
- MySQL接続
- 構造化ログ
- Typer CLI
- `.env.example`

#### Phase 1

- Alembicマイグレーション
- 商品CSV取込
- Product Research CSV取込
- 送料CSV取込
- 手数料CSV取込
- 為替CSV取込
- 3シナリオ利益計算
- 損益分岐価格
- 候補判定
- 機会スコア
- 上位候補CLI表示
- CSVエクスポート
- 監査ログ
- 単体テスト
- MySQL統合テスト
- E2Eサンプル

### 実装順

以下の順序を崩さないでください。

1. 既存環境の調査
2. 設定と依存関係
3. DBモデル・マイグレーション
4. Domain層のMoney/Profit/Decision
5. CSV importer
6. Repository/Service
7. CLI
8. Tests
9. README更新
10. サンプル実行

### 実装品質

- モジュール境界を明確にしてください
- APIクライアントをドメインロジックから分離してください
- DBモデルとPydanticモデルを混同しないでください
- 1関数1責務を意識してください
- 例外を握りつぶさないでください
- 再実行可能・冪等にしてください
- 変更理由が分かるログを残してください
- 候補スコアだけでなく内訳も保存してください
- 時刻はDB内UTC、表示Asia/Tokyoにしてください
- CSVの数式インジェクション対策をしてください
- 本番キーをテストへ入れないでください

### テストで必ず確認すること

- 利益計算の正常系・赤字・固定手数料・広告・返品・関税
- Conservativeシナリオ
- 損益分岐価格
- BLOCKEDの優先順位
- データ不足・鮮度切れ
- JAN一致と型番一致
- セット数・状態違いの誤マッチ防止
- CSV不正入力
- 再取込時の重複防止
- MySQL制約とトランザクション
- eBay 403時のフォールバック設計

### 完了報告に含めること

1. 実装した機能
2. 変更ファイル一覧
3. DBマイグレーション内容
4. 実行コマンド
5. テスト結果
6. サンプル出力
7. 未実装項目
8. 次に実装すべき項目
9. 既知のリスク
10. 手動で必要な認証・API申請

まずはコードを変更する前に、調査結果と実装計画を提示してください。その後、Phase 0とPhase 1を実装し、全テストを実行してください。

---

## Phase 2以降を依頼する追加プロンプト

Phase 0とPhase 1が完了し、テストが通った後に使う。

```text
既存のPhase 0・Phase 1を壊さず、docsの仕様に従ってPhase 2を実装してください。

対象:
- Yahoo!ショッピング商品検索API
- 楽天市場商品検索API
- 楽天製品検索API
- APIレスポンスの正規化
- JAN、ブランド、型番、セット数、状態を使うマッチング
- 国内価格スナップショット
- リトライ、レート制限、キャッシュ、監査ログ

条件:
- HTTPX、Pydantic、Tenacityを使用
- API障害時も既存データで計算を継続
- 外部APIのcontract testをモックで作成
- APIキーをログへ出さない
- 生レスポンスは設定で保存可能にする
- 送料込み仕入価格を計算する
- 最安値だけでなく取得件数、中央値、信頼度を保存する

実装後にRuff、pytest、MySQL統合テスト、サンプル実行を行い、結果を報告してください。
```

## eBay Browse API実装を依頼する追加プロンプト

```text
Phase 3としてeBay Browse APIアダプターを実装してください。

前提:
- Production accessの有無を設定で切り替える
- 未設定・未承認・403ではCSVモードへフォールバックする
- Finding API、Shopping API、Marketplace Insights APIを使わない
- HTMLスクレイピングを実装しない

機能:
- Client CredentialsによるApplication Token
- トークンキャッシュ
- keyword/GTIN/category検索
- pagination
- price/shipping/condition/seller country/item URL等の正規化
- 取得日時とraw payload保存
- 価格中央値と競合件数
- JAN/型番/ブランド/タイトル類似度による一致信頼度
- 429、5xx、timeoutリトライ
- contract tests

Browse APIを使えなくても、既存のCSV・国内API・利益計算が正常に動くことを維持してください。
```

<!-- END: docs/06_CLAUDE_CODE_EXECUTION_PROMPT.md -->

---

<!-- BEGIN: IMPLEMENTATION_CHECKLIST.md -->
# 実装チェックリスト

Claude Codeが作業状況を更新するためのチェックリスト。完了時に `[ ]` を `[x]` へ変更する。

## 事前調査

- [ ] リポジトリ全体を確認した
- [ ] Pythonバージョンを確認した
- [ ] MySQLまたはMariaDBの種類・バージョンを確認した
- [ ] 既存DB名・接続方法・既存マイグレーションを確認した
- [ ] 既存systemd timer、cron、CIを確認した
- [ ] 既存コードで再利用する箇所を整理した
- [ ] 破壊的変更の有無を確認した

## Phase 0: Foundation

- [ ] `pyproject.toml` を作成・更新した
- [ ] uv環境を構築した
- [ ] `uv.lock` を作成した
- [ ] Ruffを設定した
- [ ] pytestを設定した
- [ ] Pydantic Settingsを設定した
- [ ] `.env.example` を作成した
- [ ] MySQL接続確認CLIを作成した
- [ ] SQLAlchemy session管理を作成した
- [ ] Alembicを初期化した
- [ ] 構造化ログとシークレットマスクを実装した
- [ ] Typer CLIの骨組みを作成した

## Phase 1: Offline MVP

- [ ] 初期DBスキーマをAlembicで作成した
- [ ] seed用の既定ルールを作成した
- [ ] 商品CSV importerを作成した
- [ ] Product Research CSV importerを作成した
- [ ] 送料CSV importerを作成した
- [ ] 手数料CSV importerを作成した
- [ ] 為替CSV importerを作成した
- [ ] CSV取込のハッシュ・冪等性を実装した
- [ ] Money/Decimalドメインを実装した
- [ ] Base/Optimistic/Conservative計算を実装した
- [ ] 損益分岐価格を実装した
- [ ] データ信頼度を実装した
- [ ] 機会スコアを実装した
- [ ] 候補判定を実装した
- [ ] BLOCKED優先処理を実装した
- [ ] CLI表形式レポートを作成した
- [ ] CSV exportを作成した
- [ ] 監査ログを作成した
- [ ] E2Eサンプルを作成した

## Phase 2: 国内API

- [ ] 共通HTTPX clientを作成した
- [ ] timeout設定を作成した
- [ ] 429/5xx限定リトライを実装した
- [ ] Yahoo!ショッピングAPI clientを実装した
- [ ] 楽天市場API clientを実装した
- [ ] 楽天製品API clientを実装した
- [ ] JAN完全一致を実装した
- [ ] ブランド＋型番一致を実装した
- [ ] セット数・状態の不一致除外を実装した
- [ ] RapidFuzz補助照合を実装した
- [ ] rawレスポンス保存を実装した
- [ ] 国内価格履歴を保存した
- [ ] API contract testsを作成した

## Phase 3: eBay Browse API

- [ ] eBay機能の有効・無効設定を実装した
- [ ] Application Token取得を実装した
- [ ] トークンキャッシュを実装した
- [ ] keyword検索を実装した
- [ ] GTIN検索を実装した
- [ ] paginationを実装した
- [ ] current listingsを正規化した
- [ ] 価格中央値・競合指標を計算した
- [ ] 403/未承認時にCSVモードへフォールバックした
- [ ] Finding API等を一切使用していないことを確認した
- [ ] HTMLスクレイピングがないことを確認した
- [ ] contract testsを作成した

## Phase 4: 運用

- [ ] `finder daily` を実装した
- [ ] systemd serviceを作成した
- [ ] systemd timerを作成した
- [ ] ログ出力と終了コードを確認した
- [ ] MySQLバックアップスクリプトを作成した
- [ ] バックアップ復元手順を作成した
- [ ] GitHub Actions CIを作成した
- [ ] 本番シークレットがCIにないことを確認した

## テスト

- [ ] 利益計算正常系
- [ ] 赤字計算
- [ ] 固定・変動手数料
- [ ] 関税・広告・返品引当
- [ ] Conservativeシナリオ
- [ ] 損益分岐価格
- [ ] BLOCKED優先順位
- [ ] データ不足
- [ ] データ鮮度切れ
- [ ] JAN・型番マッチング
- [ ] 状態・セット数誤一致防止
- [ ] CSV不正入力
- [ ] CSV数式インジェクション対策
- [ ] MySQL統合テスト
- [ ] 再実行時の重複防止
- [ ] eBay 403フォールバック
- [ ] 全E2Eサンプル成功

## リリース判定

- [ ] `uv run ruff format --check .` 成功
- [ ] `uv run ruff check .` 成功
- [ ] `uv run pytest -q` 成功
- [ ] Alembic upgrade成功
- [ ] サンプルCSVからランキング生成成功
- [ ] コスト内訳が説明可能
- [ ] 規制商品が購入候補に混入しない
- [ ] READMEの導入手順が最新
- [ ] 未実装事項と既知リスクを記載した

<!-- END: IMPLEMENTATION_CHECKLIST.md -->

---

<!-- BEGIN: SOURCE_REFERENCES.md -->
# 調査ソース一覧

基準日: 2026-08-06

実装時は必ず公式ドキュメントを再確認すること。API仕様、料金、利用条件は変更される。

## MySQL

- MySQL 8.4 Reference Manual — JSON_VALUE and expression indexes  
  https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html
- MySQL 8.4 Reference Manual — Indexes on Generated Columns  
  https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html
- MySQL 8.4 Reference Manual — Multiple-Column Indexes  
  https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html

## eBay

- Browse API overview  
  https://developer.ebay.com/api-docs/buy/browse/overview.html
- Browse API search method  
  https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
- Product Research  
  https://www.ebay.com/help/selling/selling-tools/product-research?id=4853
- Marketplace Insights API overview  
  https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html
- Buy APIs production eligibility / approval  
  https://developer.ebay.com/api-docs/static/gs_ebay-rest-getting-started-landing.html
- eBay API deprecation status  
  https://developer.ebay.com/develop/get-started/api-deprecation-status
- Finding API decommission notice  
  https://developer.ebay.com/develop/apis/deprecated
- Official eBay OAuth Python client repository  
  https://github.com/eBay/ebay-oauth-python-client
- Archived unofficial Browse API Python client（採用しない）  
  https://github.com/AverHLV/browseapi

## Yahoo!ショッピング

- Yahoo!デベロッパーネットワーク ショッピング商品検索 v3  
  https://developer.yahoo.co.jp/webapi/shopping/shopping/v3/itemsearch.html

## 楽天

- 楽天市場商品検索API  
  https://webservice.rakuten.co.jp/documentation/ichiba-item-search
- 楽天製品検索API  
  https://webservice.rakuten.co.jp/documentation/ichiba-product-search

## Python / OSS

- SQLAlchemy  
  https://github.com/sqlalchemy/sqlalchemy
- Alembic  
  https://github.com/sqlalchemy/alembic
- HTTPX  
  https://github.com/encode/httpx
- Pydantic  
  https://github.com/pydantic/pydantic
- Pydantic Settings  
  https://github.com/pydantic/pydantic-settings
- Tenacity  
  https://github.com/jd/tenacity
- RapidFuzz  
  https://github.com/rapidfuzz/RapidFuzz
- Typer  
  https://github.com/fastapi/typer
- Rich  
  https://github.com/Textualize/rich
- Streamlit  
  https://github.com/streamlit/streamlit
- uv  
  https://github.com/astral-sh/uv
- Ruff  
  https://github.com/astral-sh/ruff
- pytest  
  https://github.com/pytest-dev/pytest

## 採用上の注意

- GitHubのstar数だけで採用しない
- 最終リリース、コミット頻度、Issue、Python対応版を確認する
- 公式SDKでも対象Pythonが古い場合は採用しない
- 非公式eBayスクレイパーは更新停止・規約違反・HTML変更リスクが高いため中核へ使わない
- 依存パッケージは最小限にし、ロックファイルをコミットする

<!-- END: SOURCE_REFERENCES.md -->
