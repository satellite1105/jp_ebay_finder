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
