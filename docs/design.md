# 技術設計: Japan eBay Opportunity Finder

## 0. 位置づけ

本設計書は `docs/spec.md`(F1〜F37, S1〜S13)を実装可能な構造に落とし込んだものである。DB設計・計算式・CLI仕様・OSS選定は既存資料(`docs/01〜06`, `CLAUDE.md`)を正とし、そのまま踏襲する。既存資料に明記のない部分(一部テーブルDDL、Pydantic/SQLAlchemyの具体的クラス定義、ディレクトリ内の追加ファイル分割)のみ本書で新たに確定させる(詳細は末尾「本設計で新たに確定させた事項」参照)。

## 1. アーキテクチャ概要

`docs/01_ARCHITECTURE_AND_DATABASE.md` のレイヤー構成をそのまま採用する。

```text
[CLI (Typer) / Streamlit(任意)]
        ↓
[Application Services]  ← import_service / matching_service / market_service /
                            ebay_service / opportunity_service / reporting_service / daily_service
        ↓
[Domain: Money / Profit / Scoring / Decisions / Compliance / Matching]  … 外部I/Oなし・純粋関数
        ↓
[Repositories]  … MySQL CRUD (SQLAlchemy 2.x)
        ↓
[既存MySQL (ebay_opportunity)]

Yahoo API ─────┐
Rakuten API ───┼→ Clients(Adapter) → Normalizers → Services → Repositories
eBay Browse ───┤
CSV Import ────┘→ Importers(検証) → Services → Repositories
```

レイヤーの責務(01文書どおり):
- `Config`: 環境変数(`.env`)と既定値(`pydantic-settings`)
- `Clients`: 外部API呼び出しのみ。DBへ直接書かない
- `Normalizers`: 外部レスポンス→内部Pydanticモデルへ変換
- `Matchers`: JAN/型番/商品名照合
- `Repositories`: MySQL CRUD。SQLAlchemyモデルのみ扱う
- `Domain`: 利益・スコア・判定。**外部I/Oなし・floatなし・DB/HTTP呼び出し禁止**
- `Services`: ユースケース実行(Domain+Repository+Client+Importerの組み合わせ)
- `CLI`: 操作入口(Typer)
- `Scheduler`: systemd timerから`finder daily`を呼ぶだけ(専用コードは持たない)

動作モードA/B/C(01文書どおり)。**全テストはMode C(外部APIなし)で実行可能**であることを設計の絶対条件とする。

## 2. ディレクトリ構成

`CLAUDE.md` の推奨構成をベースに、並列実装のためファイル粒度を明示化したもの。

```text
jp_ebay_finder/
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
│   ├── script.py.mako
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_seed_default_rules.py
├── src/
│   └── opportunity_finder/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── logging_config.py
│       ├── cli_commands/
│       │   ├── __init__.py
│       │   ├── db_commands.py
│       │   ├── import_commands.py
│       │   ├── fetch_commands.py
│       │   ├── calculate_commands.py
│       │   ├── report_commands.py       # report / export の両Typerサブアプリを持つ
│       │   └── daily_command.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models.py
│       │   └── repositories/
│       │       ├── __init__.py
│       │       ├── product_repository.py
│       │       ├── supplier_repository.py
│       │       ├── market_repository.py
│       │       ├── opportunity_repository.py
│       │       ├── reference_data_repository.py
│       │       └── run_repository.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── money.py
│       │   ├── models.py
│       │   ├── profit.py
│       │   ├── scoring.py
│       │   ├── decisions.py
│       │   ├── compliance.py
│       │   └── matching.py
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── yahoo_shopping.py
│       │   ├── rakuten_ichiba.py
│       │   ├── rakuten_product.py
│       │   ├── ebay_auth.py
│       │   └── ebay_browse.py
│       ├── normalizers/
│       │   ├── __init__.py
│       │   ├── yahoo_normalizer.py
│       │   ├── rakuten_normalizer.py
│       │   └── ebay_normalizer.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── import_service.py
│       │   ├── matching_service.py
│       │   ├── market_service.py       # Yahoo/Rakuten統合
│       │   ├── ebay_service.py         # eBay Browse専用(フォールバック処理含む)
│       │   ├── opportunity_service.py
│       │   ├── reporting_service.py
│       │   └── daily_service.py
│       ├── importers/
│       │   ├── __init__.py
│       │   ├── csv_common.py
│       │   ├── products_csv.py
│       │   ├── product_research_csv.py
│       │   ├── shipping_csv.py
│       │   ├── fees_csv.py
│       │   └── exchange_csv.py
│       └── exporters/
│           ├── __init__.py
│           ├── opportunities_csv.py
│           └── audit_jsonl.py
├── dashboard/
│   └── app.py                          # 任意(N1)
├── scripts/
│   ├── daily_run.sh
│   ├── backup_mysql.sh
│   ├── restore_mysql_example.sh
│   └── check_no_secrets.sh
├── deploy/
│   └── systemd/
│       ├── opportunity-finder.service
│       └── opportunity-finder.timer
├── data/
│   ├── samples/
│   │   ├── products.csv
│   │   ├── product_research.csv
│   │   ├── shipping_rates.csv
│   │   ├── fee_profiles.csv
│   │   └── exchange_rates.csv
│   └── imports/.gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
└── .github/
    └── workflows/
        └── ci.yml
```

## 3. DB設計(MySQL 8.0+ / InnoDB / utf8mb4)

`01_ARCHITECTURE_AND_DATABASE.md` のDDLをそのまま正本として引用する(**書き換えない**)。全テーブルをAlembic migrationで管理し、`migrations/versions/0001_initial_schema.py` に集約する。データ型ルール(金額`DECIMAL(18,4)`/外貨`DECIMAL(18,6)`、率`DECIMAL(10,6)`、日時`DATETIME(6)`でUTC保存、`ENUM`不使用・`status`は`VARCHAR(32)`)も01文書どおり。

### 3.1 引用DDL(01文書より、正本)

`products` / `supplier_items` / `supplier_price_snapshots` / `market_queries` / `market_research_metrics` / `opportunity_snapshots` — 全カラム・インデックス・制約は `docs/01_ARCHITECTURE_AND_DATABASE.md` 9節のDDLをそのまま使用する。実装タスク(T04/T05)はこのファイルを参照し、DDLを一字一句変更せずSQLAlchemyモデルへ写像すること。

### 3.2 本設計で新規に確定させたDDL(01文書に「他のテーブルも同じ原則で実装する」とのみ記載され、具体DDLが無かったため、01の型ルール・命名規則・インデックス方針に厳密に従い本書で確定させる)

```sql
CREATE TABLE ebay_listings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    query_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'EBAY_BROWSE',
    external_item_id VARCHAR(255) NOT NULL,
    title VARCHAR(512) NOT NULL,
    item_url TEXT NULL,
    condition_raw VARCHAR(64) NULL,
    condition_normalized VARCHAR(32) NULL,
    seller_country CHAR(2) NULL,
    match_method VARCHAR(32) NOT NULL,
    match_confidence DECIMAL(10,6) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at DATETIME(6) NOT NULL,
    last_seen_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_ebay_listings_query FOREIGN KEY (query_id) REFERENCES market_queries(id),
    CONSTRAINT fk_ebay_listings_product FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE KEY uq_ebay_listing_external (source, external_item_id),
    KEY ix_ebay_listing_query (query_id, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ebay_listing_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ebay_listing_id BIGINT UNSIGNED NOT NULL,
    price_usd DECIMAL(18,6) NOT NULL,
    shipping_usd DECIMAL(18,6) NOT NULL DEFAULT 0,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    quantity_available INT UNSIGNED NULL,
    captured_at DATETIME(6) NOT NULL,
    raw_payload JSON NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_ebay_snapshot_listing FOREIGN KEY (ebay_listing_id) REFERENCES ebay_listings(id),
    UNIQUE KEY uq_ebay_snapshot_capture (ebay_listing_id, captured_at),
    KEY ix_ebay_snapshot_latest (ebay_listing_id, captured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE exchange_rates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    base_currency CHAR(3) NOT NULL,
    quote_currency CHAR(3) NOT NULL,
    rate DECIMAL(18,8) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    effective_at DATETIME(6) NOT NULL,
    raw_payload JSON NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_exchange_rate_point (base_currency, quote_currency, effective_at),
    KEY ix_exchange_rate_latest (base_currency, quote_currency, effective_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE shipping_rates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile_code VARCHAR(64) NOT NULL,
    destination_country CHAR(2) NOT NULL,
    min_weight_g INT UNSIGNED NOT NULL,
    max_weight_g INT UNSIGNED NOT NULL,
    service_name VARCHAR(128) NOT NULL,
    shipping_jpy DECIMAL(18,4) NOT NULL,
    tracking BOOLEAN NOT NULL DEFAULT TRUE,
    included_insurance_jpy DECIMAL(18,4) NOT NULL DEFAULT 0,
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    import_batch_id BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_shipping_lookup (profile_code, destination_country, min_weight_g, max_weight_g),
    KEY ix_shipping_effective (effective_from, effective_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE fee_rules (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile_code VARCHAR(64) NOT NULL,
    marketplace VARCHAR(32) NOT NULL,
    category_code VARCHAR(64) NULL,
    variable_fee_rate DECIMAL(10,6) NOT NULL,
    international_fee_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    fixed_fee_currency CHAR(3) NOT NULL,
    fixed_fee_amount DECIMAL(18,6) NOT NULL DEFAULT 0,
    ad_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    return_reserve_rate DECIMAL(10,6) NOT NULL DEFAULT 0,
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    import_batch_id BIGINT UNSIGNED NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_fee_rule_profile (profile_code, effective_from),
    KEY ix_fee_rule_lookup (marketplace, category_code, effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE scan_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id CHAR(36) NOT NULL,
    command VARCHAR(64) NOT NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    rows_read INT UNSIGNED NOT NULL DEFAULT 0,
    rows_written INT UNSIGNED NOT NULL DEFAULT 0,
    failure_count INT UNSIGNED NOT NULL DEFAULT 0,
    summary JSON NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_scan_run_id (run_id),
    KEY ix_scan_run_command_time (command, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE import_batches (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    import_type VARCHAR(32) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    rows_total INT UNSIGNED NOT NULL DEFAULT 0,
    rows_imported INT UNSIGNED NOT NULL DEFAULT 0,
    rows_quarantined INT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    quarantine_detail JSON NULL,
    imported_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_import_batch_hash (import_type, file_sha256),
    KEY ix_import_batch_time (import_type, imported_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE audit_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id CHAR(36) NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id BIGINT UNSIGNED NULL,
    action VARCHAR(64) NOT NULL,
    actor VARCHAR(64) NOT NULL DEFAULT 'system',
    before_value JSON NULL,
    after_value JSON NULL,
    reason TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_audit_entity (entity_type, entity_id),
    KEY ix_audit_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

インデックス方針(01文書どおり): 最新取得`(entity_id, captured_at)`、ランキング`(scenario, decision, opportunity_score)`、商品照合はJAN/ブランド+型番、JSON内頻出値は通常列へ昇格。

Migration方針: `0001_initial_schema`(全テーブル一括作成)→`0002_seed_default_rules`(`fee_rules`/`shipping_rates`/`candidate_rules`相当の初期データ投入。破壊的変更は自動実行しない。カラム削除は2段階(廃止マーク→後続migrationで削除))。

## 4. 技術スタック(選定理由つき)

`CLAUDE.md`/`02_DATA_APIS_AND_OSS.md` の選定をそのまま採用する。

| 用途 | 採用 | 選定理由 |
|---|---|---|
| 言語/パッケージ管理 | Python 3.11+ / `uv` | lockfile・Python管理・CI連携が容易。ユーザー得意技術(Python) |
| ORM | SQLAlchemy 2.x | MySQL対応が成熟、型付き`Mapped`記法 |
| Migration | Alembic | SQLAlchemy標準、破壊的変更を制御しやすい |
| MySQL driver | PyMySQL | Pure Python、軽量、追加ビルド不要 |
| HTTP | httpx | 同期クライアント、timeout/pool制御が明示的 |
| 入力検証 | Pydantic 2.x | API/CSV境界の検証に標準的 |
| 設定 | pydantic-settings | `.env`の型検証 |
| リトライ | tenacity | 上限付きexponential backoff+jitterが簡潔に書ける |
| 文字列類似度 | RapidFuzz | 高速・C実装、商品名照合に定評 |
| CLI | Typer | 型ヒントからサブコマンド自動生成、テストしやすい(`CliRunner`) |
| 表示 | Rich | Typerと親和性が高い表出力 |
| テスト | pytest / pytest-cov / respx | 標準的、HTTPXモックに`respx`が公式に近い |
| lint/format | Ruff | 単一ツールでlint+format |
| UI(任意) | Streamlit | Pythonのみで管理画面。MVP必須要件にしない |

新規に導入するDB/ミドルウェア(PostgreSQL, DuckDB, Supabase, Elasticsearch, Redis, メッセージキュー, Airflow/Dagster/Prefect等)は一切追加しない(S1)。

## 5. ドメインロジック設計(外部I/Oなしの原則)

`domain/` 配下は **DB接続・HTTP呼び出し・ファイルI/Oを一切行わない**。全ての値は引数として渡し、戻り値として返す純粋関数/不変値オブジェクトのみで構成する(YAML設定やDB上のルール値の読み込みはService層の責務)。

### 5.1 `domain/money.py` — 金額型

```python
from decimal import Decimal, ROUND_HALF_UP

JPY_QUANT = Decimal("0.0001")   # DECIMAL(18,4)
USD_QUANT = Decimal("0.000001") # DECIMAL(18,6)
RATE_QUANT = Decimal("0.000001")

class Money:
    """Decimal専用の金額値オブジェクト。float入力は禁止(TypeError)。"""
    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal | str | int, currency: str) -> None:
        if isinstance(amount, float):
            raise TypeError("Money must not be constructed from float")
        self.amount: Decimal = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        self.currency = currency

    def quantize(self, exp: Decimal = JPY_QUANT, rounding=ROUND_HALF_UP) -> "Money": ...
    def __add__(self, other: "Money") -> "Money": ...  # 通貨不一致はValueError
    def __sub__(self, other: "Money") -> "Money": ...
    def __mul__(self, rate: Decimal) -> "Money": ...   # rateはDecimal限定
    def __eq__(self, other: object) -> bool: ...
    def as_decimal(self) -> Decimal: ...
```

`domain/profit.py`等の内部計算でのみ`Money`を使用する。境界(Pydanticモデル)では`Decimal`フィールドを直接使う(下記5.2)。

### 5.2 `domain/models.py` — 境界Pydanticモデル(全ドメイン共通・T04で確定)

```python
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

Scenario = Literal["optimistic", "base", "conservative"]
Decision = Literal[
    "BLOCKED", "MISSING_DATA", "STALE_DATA", "REVIEW_COMPLIANCE",
    "LOW_DEMAND", "LOW_PROFIT", "WATCH", "BUY_TEST_1", "BUY_TEST_2", "REPLENISH",
]

class ProductInput(BaseModel):
    external_key: str
    jan_code: str | None = Field(default=None, pattern=r"^\d{8}(\d{5})?$")
    title: str
    brand: str | None = None
    model_number: str | None = None
    condition: Literal["new", "used"]
    source_cost_jpy: Decimal = Field(ge=0)
    source_shipping_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    weight_g: int = Field(gt=0)
    packed_weight_g: int | None = Field(default=None, gt=0)
    origin_country: str = Field(pattern=r"^[A-Z]{2}$")
    supplier_name: str | None = None
    supplier_url: str | None = None
    checked_at: datetime  # tz-aware必須

class SupplierOffer(BaseModel):
    source: str
    external_item_id: str
    title: str
    item_price_jpy: Decimal = Field(ge=0)
    domestic_shipping_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    points_value_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    coupon_value_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    available: bool
    jan_code: str | None = None
    brand: str | None = None
    model_number: str | None = None
    captured_at: datetime
    raw_payload: dict | None = None

    @property
    def effective_cost_jpy(self) -> Decimal:
        """最安値ではなく送料込み実質価格(F29)。"""
        return (self.item_price_jpy + self.domestic_shipping_jpy
                - self.points_value_jpy - self.coupon_value_jpy)

class MarketResearchInput(BaseModel):
    external_key: str
    search_query: str
    marketplace: str = "EBAY_US"
    condition: Literal["new", "used"] | None = None
    lookback_days: int = Field(gt=0)
    sold_count: int | None = Field(default=None, ge=0)
    active_count: int | None = Field(default=None, ge=0)
    median_sold_price_usd: Decimal | None = Field(default=None, ge=0)
    average_sold_price_usd: Decimal | None = Field(default=None, ge=0)
    median_buyer_shipping_usd: Decimal = Field(default=Decimal("0"), ge=0)
    sell_through_rate: Decimal | None = Field(default=None, ge=0, le=1)
    checked_at: datetime
    notes: str | None = None

class FeeProfile(BaseModel):
    profile_code: str
    marketplace: str
    category_code: str | None = None
    variable_fee_rate: Decimal = Field(ge=0, le=1)
    international_fee_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    fixed_fee_currency: str
    fixed_fee_amount: Decimal = Field(ge=0)
    ad_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    return_reserve_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    effective_from: datetime
    effective_to: datetime | None = None

class ShippingQuote(BaseModel):
    profile_code: str
    destination_country: str = Field(pattern=r"^[A-Z]{2}$")
    min_weight_g: int = Field(ge=0)
    max_weight_g: int = Field(gt=0)
    service_name: str
    shipping_jpy: Decimal = Field(ge=0)
    tracking: bool
    included_insurance_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    effective_from: datetime
    effective_to: datetime | None = None

class ScenarioMultipliers(BaseModel):
    sale_price_multiplier: Decimal
    exchange_rate_multiplier: Decimal
    shipping_multiplier: Decimal
    ad_rate_multiplier: Decimal
    return_rate_multiplier: Decimal

class ProfitInput(BaseModel):
    item_price_usd: Decimal = Field(ge=0)
    buyer_shipping_usd: Decimal = Field(default=Decimal("0"), ge=0)
    exchange_rate_jpy_per_usd: Decimal = Field(gt=0)
    source_item_cost_jpy: Decimal = Field(ge=0)
    source_domestic_shipping_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    source_transport_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    packaging_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    international_shipping_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    duty_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    import_processing_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    international_fee_rate: Decimal = Field(default=Decimal("0"), ge=0)
    currency_conversion_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    payment_fee_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    labor_cost_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    other_cost_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    marketplace_fee_rate: Decimal = Field(ge=0)
    marketplace_fixed_fee_jpy: Decimal = Field(default=Decimal("0"), ge=0)
    fee_base_is_item_price_only: bool = True  # Falseなら購入者送料込みをfee_baseにする
    ad_rate: Decimal = Field(default=Decimal("0"), ge=0)
    return_reserve_rate: Decimal = Field(default=Decimal("0"), ge=0)
    cash_required_before_sale_jpy: Decimal = Field(gt=0)
    target_profit_jpy: Decimal = Field(default=Decimal("3000"), ge=0)

class ProfitScenarioResult(BaseModel):
    scenario: Scenario
    buyer_total_usd: Decimal
    recognized_revenue_jpy: Decimal
    marketplace_fee_jpy: Decimal
    promoted_listing_jpy: Decimal
    return_reserve_jpy: Decimal
    total_cost_jpy: Decimal
    net_profit_jpy: Decimal
    net_margin: Decimal
    capital_efficiency: Decimal
    break_even_buyer_total_usd: Decimal
    target_price_usd: Decimal

class ComplianceDecision(BaseModel):
    compliance_status: Literal["approved", "review", "blocked", "needs_review"]
    flags: list[str] = Field(default_factory=list)

class OpportunityResult(BaseModel):
    product_id: int
    query_id: int
    scenarios: dict[Scenario, ProfitScenarioResult]
    opportunity_score: Decimal
    score_breakdown: dict[str, Decimal]
    confidence_score: Decimal
    confidence_breakdown: dict[str, Decimal]
    decision: Decision
    reason_codes: list[str]
    input_snapshot: dict
```

**後方互換ルール**: 実装中に必要になったフィールドは追加してよいが、上記に定義した既存フィールド名・型は変更しない(依存タスクとの契約破壊を防ぐため)。

### 5.3 計算式(`domain/profit.py`) — `03_PROFIT_AND_SCORING.md` をそのまま採用

```text
buyer_total_usd = item_price_usd + buyer_shipping_usd
recognized_revenue_jpy = buyer_total_usd × exchange_rate_jpy_per_usd
variable_marketplace_fee_jpy = fee_base_jpy × marketplace_fee_rate
marketplace_fee_jpy = variable_marketplace_fee_jpy + marketplace_fixed_fee_jpy
promoted_listing_jpy = ad_fee_base_jpy × promoted_listing_rate
return_reserve_jpy = recognized_revenue_jpy × return_reserve_rate
total_cost_jpy = source_item_cost_jpy + source_domestic_shipping_jpy + source_transport_jpy
  + packaging_jpy + international_shipping_jpy + duty_jpy + import_processing_jpy
  + marketplace_fee_jpy + international_fee_jpy + currency_conversion_jpy
  + promoted_listing_jpy + payment_fee_jpy + return_reserve_jpy + labor_cost_jpy + other_cost_jpy
net_profit_jpy = recognized_revenue_jpy - total_cost_jpy
net_margin = net_profit_jpy / recognized_revenue_jpy   # revenue=0はZeroDivisionを回避しNoneまたは0を返す
capital_efficiency = net_profit_jpy / cash_required_before_sale_jpy
break_even_revenue_jpy = fixed_cost_jpy / (1 - total_variable_rate)
break_even_buyer_total_usd = break_even_revenue_jpy / exchange_rate_jpy_per_usd
target_revenue_jpy = (fixed_cost_jpy + target_profit_jpy) / (1 - total_variable_rate)
```

3シナリオ乗数(Optimistic/Base/Conservative)は`ScenarioMultipliers`として引数で渡す(既定値はspec.md「三つの採算シナリオ」表のとおりだが、コード直書きせず`config/settings.example.yaml`または`fee_rules`/DB由来の値をService層が注入する)。

`domain/scoring.py`: 機会スコア(0〜100、内訳25/15/15/10/10/10/10/5/-30)とデータ信頼度スコア(0〜100、JAN+35等の配点)をspec.md「機会スコア」「データ信頼度配点」表のとおり実装。両スコアとも根拠値を`dict[str, Decimal]`で返す。

`domain/decisions.py` + `domain/compliance.py`: 優先順位 `BLOCKED > MISSING_DATA > STALE_DATA > REVIEW_COMPLIANCE > LOW_DEMAND > LOW_PROFIT > WATCH > BUY_TEST_1/2 > REPLENISH` をspec.md「判定例」のif-elif連鎖のとおり実装。`compliance.py`は`compliance_status`(`approved`/`review`/`blocked`/`needs_review`)からBLOCKED/REVIEW_COMPLIANCE判定に必要な情報のみを返す小さい関数群。

`domain/matching.py`: JAN完全一致→ブランド+型番一致→RapidFuzz類似度の順で判定し、セット数・状態(新品/中古)不一致は問答無用で不一致として除外(F27)。戻り値は`match_method`(`"jan"`/`"brand_model"`/`"fuzzy_title"`/`"none"`)と`match_confidence: Decimal`。

## 6. APIクライアント設計

### 6.1 共通実装(`clients/base.py`)

- `httpx.Client`(同期)。connect/readタイムアウトは`Settings`から注入
- リトライは**429と5xx限定**(400/401/403/404は無条件リトライしない)。`tenacity`で`wait_exponential_jitter` + 最大試行回数
- リクエストごとに`request_id`(uuid4)を発行しログ・raw_payload保存に付与
- 認証情報(Authorizationヘッダー・APIキー)はログ出力前に必ずマスク
- raw responseは呼び出し元がJSON列(`raw_payload`)へ保存できるようクライアントは生dictも返す
- レスポンスはPydanticモデルで検証(信用しない)

### 6.2 個別クライアント

| クライアント | 仕様要点 |
|---|---|
| `yahoo_shopping.py` | 商品検索v3。検索順 `jan_code`→`query`(F23) |
| `rakuten_ichiba.py` | Ichiba Item Search。製品名・型番から販売中商品(価格/在庫/ストア/URL)(F24) |
| `rakuten_product.py` | Product Search。JANから製品情報(製品名/ブランド/型番)(F25) |
| `ebay_auth.py` | Client Credentials(Application Token)、トークンキャッシュ(有効期限管理) |
| `ebay_browse.py` | keyword/GTIN検索、ページネーションは`next`優先、Production未承認・403・権限不足で例外を投げ、`ebay_service.py`側でCSVモードへフォールバック(F30〜F32) |

廃止済みFinding API/Shopping API、Marketplace Insights APIは実装しない(F32)。

## 7. CLIコマンド設計(`04_IMPLEMENTATION_AND_TESTS.md` のCLI仕様をそのまま採用)

CLI名 `finder`。`cli.py`が各`cli_commands/*.py`のTyperサブアプリを束ねる。

```text
finder db check|upgrade|current
finder import products|product-research|shipping|fees|exchange <path>
finder fetch domestic --source yahoo|rakuten --limit N
finder fetch ebay --query-id N
finder fetch all --stale-only
finder calculate opportunities
finder calculate opportunity --product-id N
finder calculate break-even --product-id N
finder report top --limit N [--decision X] [--format table]
finder export opportunities <path>
finder export audit <path>
finder daily --stale-only --export-dir <dir>
```

`report`/`export`は同一ファイル`cli_commands/report_commands.py`内に2つのTyperサブアプリ(`report_app`, `export_app`)として実装し、`cli.py`が`app.add_typer(report_app, name="report")` / `app.add_typer(export_app, name="export")`で束ねる。

`daily`処理順(F34、04文書どおり): ①DB接続確認 ②設定検証 ③為替更新 ④古い国内価格のみ更新 ⑤eBay API利用可能なら更新 ⑥Product Research新規CSV取込 ⑦機会スナップショット計算 ⑧上位候補CSV出力 ⑨実行サマリー出力 ⑩失敗件数閾値超過で非0終了。

## 8. テスト戦略

### フレームワーク
- pytest / pytest-cov(カバレッジ計測) / respx(HTTPXモック)
- ドメイン層カバレッジ90%以上、全体80%以上(S11)

### テスト分類と配置
| 種別 | 配置 | 対象 | ネットワーク/DB |
|---|---|---|---|
| Unit | `tests/unit/` | domain/*, importers/*(パース・検証のみ) | 不要 |
| Contract | `tests/contract/` | clients/*(respxでHTTPモック) | 不要(モックのみ) |
| Integration | `tests/integration/` | repositories/*, services/*, cli_commands/*, E2E | **実MySQL(テスト専用DB)必須。SQLiteで代替しない** |

### テスト用MySQLの用意方法
ローカル開発:
```bash
docker run --rm -d --name finder-test-mysql \
  -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=finder_test \
  -e MYSQL_USER=finder -e MYSQL_PASSWORD=finder -p 3306:3306 mysql:8.4
export MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_DATABASE=finder_test \
       MYSQL_USER=finder MYSQL_PASSWORD=finder
uv run alembic upgrade head
```
CI: `.github/workflows/ci.yml`内のMySQLサービスコンテナ(`mysql:8.4`)を使用(05文書の例をそのまま採用)。

`tests/conftest.py`が上記環境変数からテスト用エンジン/セッションのfixtureを提供し、各integrationテストはテスト内でトランザクションrollbackまたはテーブルtruncateにより独立性を保つ。

### 全テスト実行コマンド(フェーズ4でリーダーが叩く)
```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run alembic upgrade head
uv run pytest -q
uv run pytest --cov=src/opportunity_finder --cov-report=term-missing -q
```
個別実行: `uv run pytest tests/unit -q` / `uv run pytest tests/contract -q` / `uv run pytest tests/integration -q`

## 9. 実行方法(開発時)

```bash
uv sync
cp .env.example .env   # MySQL接続情報・APIキーを設定(.envはGit管理しない)
uv run alembic upgrade head
uv run finder --help
uv run finder import products data/samples/products.csv
uv run finder calculate opportunities
uv run finder report top --limit 10
```

## 10. 実装順序(Phase 0〜4)

`06_CLAUDE_CODE_EXECUTION_PROMPT.md` の10段階順序(①既存環境調査→②設定/依存関係→③DBモデル/マイグレーション→④Domain(Money/Profit/Decision)→⑤CSV importer→⑥Repository/Service→⑦CLI→⑧Tests→⑨README更新→⑩サンプル実行)を踏襲し、これを並列タスク分割(`tasks.md`)の依存関係の基盤とする。

1. **Phase 0(基盤)**: 依存関係管理・設定・ログ・DBモデル・Domain Pydanticモデル・Alembic初期スキーマ・テストハーネス・CLI骨組み — `tasks.md` の T01〜T07(全て単独実行・逐次)
2. **Phase 1(オフラインMVP)**: Domain計算ロジック・CSV importer・Repository・Service・CLIコマンド実装・サンプルE2E — T08〜T29(バッチ1〜2、並列実行可)
3. **Phase 2(国内API)**: 共通HTTPXクライアント・Yahoo/楽天クライアント・マッチング統合 — T30〜T34(バッチ3、並列実行可)
4. **Phase 3(eBay Browse API)**: OAuth・Browse API・CSVフォールバック — T35〜T37(バッチ4)
5. **Phase 4(運用)**: systemd・バックアップ・CI・README確定 — T38〜T41(バッチ5、並列実行可)
6. **任意**: Streamlit管理画面 — T42(nice-to-have、MVP必須外)

各Phaseの完了条件はspec.mdのF番号・S番号でトレース可能(`tasks.md`の「対応要件」列参照)。

## 11. 本設計で新たに確定させた事項(既存資料に明記がなかったため本書で決定)

- **A5**: `ebay_listings`/`ebay_listing_snapshots`/`exchange_rates`/`shipping_rates`/`fee_rules`/`scan_runs`/`import_batches`/`audit_logs`のDDLは、01文書に「他のテーブルも同じ原則で実装する」という指示のみで具体DDLが無かったため、01文書の型ルール・命名規則・インデックス方針に厳密に従い本書§3.2で新規に確定した。
- **A6**: `domain/models.py`のPydanticクラス定義(フィールド名・型)は、04文書「最低限必要なモデル」のクラス名リストのみが存在したため、spec.mdのCSV仕様・DDL・計算式から矛盾なく導出して本書§5.2で確定した。
- **A7**: `Money`クラスはドメイン内部計算専用とし、Pydantic境界モデルのフィールドは`Decimal`を直接使う設計とした(Pydantic v2で任意クラスをフィールド型にする複雑さを避けるため)。
- **A8**: CLIの`report`/`export`を同一ファイル`cli_commands/report_commands.py`にまとめる、`fetch`コマンドをPhase2(国内)とPhase3(eBay)で同一ファイルに逐次追記する、という実装順序上の整理は本書で新規に確定した(既存資料はファイル分割まで指定していないため)。
