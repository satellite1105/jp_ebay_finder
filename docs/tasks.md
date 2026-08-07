# タスク分割

凡例: 「状態」は全て `[ ]`(未着手)。「executor」列は原則 `codex`。並列実行可能なタスクは同一バッチ内にまとめてあるが、`depends_on`さえ満たしていれば異なるバッチのタスクを前倒しで並列実行してもよい(例: T38はT07完了後すぐ着手可能)。

> 2026-08-07: CodexクォータをユーザーがGUI上で誤認識(実際は残り97%)したことによる一時中断があったが、誤認と判明したため解除し、autodevを通常どおり再開した。中断は技術的失敗によるものではない。

## 先行タスク(単独実行・他タスクの前提)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T01 | プロジェクト雛形 | `pyproject.toml`, `.gitignore`, `.env.example`, `alembic.ini`, `README.md`(骨子のみ) | - | F1,F2,F3 | `uv sync` が成功、`uv run ruff check .` がエラーなく実行できる(対象ファイルが空でも成功) | [x] | codex(検証済み) |
| T02 | 設定・ログ基盤 | `src/opportunity_finder/__init__.py`, `src/opportunity_finder/config.py`, `src/opportunity_finder/logging_config.py` | T01 | F4,F5 | `tests/unit/test_config.py`, `tests/unit/test_logging_config.py` を新規作成し `uv run pytest tests/unit/test_config.py tests/unit/test_logging_config.py -q` | [x] | codex |
| T03 | Moneyドメイン | `src/opportunity_finder/domain/__init__.py`, `src/opportunity_finder/domain/money.py` | T01 | F12(基盤) | `tests/unit/test_money.py`(Decimal変換/丸め/float入力拒否/通貨不一致エラー) を作成し `uv run pytest tests/unit/test_money.py -q` | [x] | codex |
| T04 | DBモデル+ドメインPydanticモデル+パッケージ雛形 | `src/opportunity_finder/db/__init__.py`, `db/base.py`, `db/session.py`, `db/models.py`, `db/repositories/__init__.py`, `src/opportunity_finder/domain/models.py`, `importers/__init__.py`, `importers/csv_common.py`, `services/__init__.py`, `exporters/__init__.py`, `clients/__init__.py`, `normalizers/__init__.py` | T02,T03 | F7(スキーマ定義) | `tests/unit/test_domain_models.py`(境界値検証: 負数金額拒否/JANパターン/国コード2文字/tz-aware日時)、`uv run python -c "from opportunity_finder.db import models"` がimportエラーなく通る | [x] | codex |
| T05 | Alembic初期マイグレーション+YAML設定 | `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial_schema.py`, `migrations/versions/0002_seed_default_rules.py`, `config/settings.example.yaml`, `config/candidate_rules.yaml`, `config/risk_rules.yaml`, `config/fee_profiles.example.yaml` | T04 | F7,F10(設定) | `uv run alembic upgrade head` がテスト用MySQLに対して成功、`uv run alembic downgrade base` も成功 | [x] | codex(実装)+リーダー(実DB検証代行。理由: Codexサンドボックスから127.0.0.1:3306へソケット接続不可のため) |
| T06 | テストハーネス | `tests/__init__.py`, `tests/conftest.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/contract/__init__.py`, `tests/fixtures/__init__.py` | T05 | S10,S11(基盤) | `uv run pytest --collect-only -q` がエラーなく完了(テスト0件でも収集失敗しないこと) | [x] | codex |
| T07 | CLI骨組み+コマンドスタブ | `src/opportunity_finder/cli.py`, `cli_commands/__init__.py`, `cli_commands/db_commands.py`(スタブ), `cli_commands/import_commands.py`(スタブ), `cli_commands/fetch_commands.py`(スタブ), `cli_commands/calculate_commands.py`(スタブ), `cli_commands/report_commands.py`(スタブ、`report_app`/`export_app`両方定義), `cli_commands/daily_command.py`(スタブ) | T02 | F6 | `uv run finder --help` が非0終了せず全サブコマンド名が表示される | [x] | codex |

**T01〜T07 実装メモ(自己完結用)**
- T01: `pyproject.toml`は`[project.dependencies]`に`sqlalchemy>=2.0,<2.1`, `alembic>=1.17,<2`, `pymysql>=1.1,<2`, `httpx>=0.28,<1`, `pydantic>=2.12,<3`, `pydantic-settings>=2.10,<3`, `tenacity>=9,<10`, `rapidfuzz>=3,<4`, `typer>=0.24,<1`, `rich>=14,<15`を含め、`[dependency-groups.dev]`(または`[project.optional-dependencies]`)に`pytest`, `pytest-cov`, `respx`, `ruff`を追加する。Ruff設定は`[tool.ruff]`セクションに記述。pytest設定(`[tool.pytest.ini_options]`)で`testpaths = ["tests"]`を指定。`.env.example`は`docs/05_OPERATIONS_AND_SECURITY.md`§3の内容をそのまま使用(全フェーズのAPIキー変数を含む。以後のタスクはこのファイルを再編集しない)。
- T02: `config.py`は`pydantic-settings`の`BaseSettings`で`.env`からMySQL接続・`EBAY_*`/`YAHOO_*`/`RAKUTEN_*`等を読み込む`Settings`クラスを定義。`logging_config.py`はstructlog相当の構造化ログ(標準`logging`+JSON Formatterでも可)を設定し、`mask_secret(value: str) -> str`関数でAPIキー/Authorizationヘッダー/MySQLパスワードをログ出力前にマスクする関数を提供。
- T03: 設計書§5.1の`Money`クラスをそのまま実装。
- T04: 設計書§3(DDL)に1:1対応する`db/models.py`(SQLAlchemy 2.x `Mapped`/`mapped_column`宣言的モデル。テーブル名・カラム名はDDLと完全一致させる)と、設計書§5.2の`domain/models.py`をそのまま実装。他の空`__init__.py`はパッケージ化のためだけの空ファイル。
- T05: `migrations/versions/0001_initial_schema.py`はT04の`db/models.py`の全テーブルを作成するAlembic revisionを手書き(autogenerateに依存しすぎない。DDLは設計書§3を正とする)。`0002_seed_default_rules.py`は`fee_rules`/`shipping_rates`にspec.mdのサンプル値(`EBAY_US_DEFAULT`等)を初期投入。YAMLファイルはspec.mdの`candidate_rules`(minimum_base_profit_jpy: 3000等)、シナリオ乗数(Optimistic/Base/Conservative)をそのまま記述。
- T06: `conftest.py`は環境変数`MYSQL_HOST`等からテスト用DBエンジンを作る`db_engine`/`db_session` fixtureと、各テスト後にテーブルをtruncateする`clean_db` fixtureを提供。
- T07: `cli.py`は設計書§7のとおり`app.add_typer(...)`で各サブアプリを束ねる。各`cli_commands/*.py`スタブは`app = typer.Typer()`と各コマンド名(例: `db check`, `db upgrade`, `db current`)だけを`NotImplementedError`または`"not implemented yet"`表示で仮実装し、`--help`が全コマンド名を表示できる状態にする。以降のタスク(T25〜T28,T34,T37)がこの中身を実装で置き換える(ファイル所有者はスタブ作成後、実装タスクへ引き継がれる。同時並列で同一ファイルを触るタスクは存在しない)。

## バッチ1(並列実行可能、T04完了後に着手可)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T08 | Profitドメイン | `domain/profit.py`, `tests/unit/test_profit.py` | T04,T03 | F13,F14 / S3,S5 | `uv run pytest tests/unit/test_profit.py -q`(正常系/固定手数料/広告なし/関税なし/赤字/0除算回避/Conservative/損益分岐を手計算値と1円以内で一致検証) | [x] | codex |
| T09 | Scoringドメイン | `domain/scoring.py`, `tests/unit/test_scoring.py` | T04 | F15,F16 | `uv run pytest tests/unit/test_scoring.py -q`(上限/下限/0件/高利益低需要/低利益高需要/リスク控除) | [x] | codex |
| T10 | Decisions+Complianceドメイン | `domain/decisions.py`, `domain/compliance.py`, `tests/unit/test_decisions.py` | T04 | F17 / S6,S7 | `uv run pytest tests/unit/test_decisions.py -q`(BLOCKED最優先/データ不足/データ鮮度/BUY_TEST_1・2/REPLENISH。`compliance_status=blocked`なら他条件に関わらず`BLOCKED`になることを必須検証) | [x] | codex |
| T11 | Matchingドメイン | `domain/matching.py`, `tests/unit/test_matching.py` | T04 | F27 | `uv run pytest tests/unit/test_matching.py -q`(JAN完全一致/型番一致/セット数違い/新品中古違い/RapidFuzz類似度/ブランド誤一致) | [x] | codex |
| T12 | 商品CSV importer | `importers/products_csv.py`, `tests/unit/test_products_csv_importer.py` | T04 | F8,F11 | `uv run pytest tests/unit/test_products_csv_importer.py -q`(正常/必須列欠落/重複行/文字コード/不正日付/不正数値/SHA-256ハッシュ計算/不正行の隔離継続) | [x] | codex |
| T13 | Product Research CSV importer | `importers/product_research_csv.py`, `tests/unit/test_product_research_csv_importer.py` | T04 | F9,F11 | `uv run pytest tests/unit/test_product_research_csv_importer.py -q`(同上観点) | [x] | codex |
| T14 | 送料表・手数料表CSV importer | `importers/shipping_csv.py`, `importers/fees_csv.py`, `tests/unit/test_shipping_fees_csv_importer.py` | T04 | F10,F11 | `uv run pytest tests/unit/test_shipping_fees_csv_importer.py -q` | [x] | codex |
| T15 | 為替CSV importer | `importers/exchange_csv.py`, `tests/unit/test_exchange_csv_importer.py` | T04 | F10,F11 | `uv run pytest tests/unit/test_exchange_csv_importer.py -q` | [x] | codex |

**バッチ1 実装メモ**
- T08: 設計書§5.3の計算式をそのまま実装。関数シグネチャ例: `def calculate_scenario(input: ProfitInput, multipliers: ScenarioMultipliers) -> ProfitScenarioResult`。`domain/models.py`(T04)の`ProfitInput`/`ProfitScenarioResult`/`ScenarioMultipliers`をそのまま使用。`net_margin`計算時は`recognized_revenue_jpy == 0`をガードしゼロ除算を回避(0を返す)。
- T09: spec.md「機会スコア」表・正規化例(`profit_score = min(max((base_profit_jpy-1000)/5000,0),1)*25`等)と「データ信頼度配点」表をそのまま実装。関数例: `def calculate_opportunity_score(...) -> tuple[Decimal, dict[str, Decimal]]`, `def calculate_confidence_score(...) -> tuple[Decimal, dict[str, Decimal]]`。
- T10: spec.md「判定例」のif-elif連鎖を`decisions.py`に実装し、`compliance.py`は`compliance_status`から`is_blocked`/`needs_review`を返す小関数を提供。`decisions.py`が`compliance.py`をimportする(同タスク内なので問題なし)。
- T11: RapidFuzzの`fuzz.token_sort_ratio`等を使用。JAN一致→ブランド+型番一致→タイトル類似度90%以上、の優先順で判定し、`unit_count`(セット数)または`condition`(新品/中古)が異なれば強制的に不一致(`match_method="none"`)とする。
- T12〜T15: 共通で`importers/csv_common.py`(T04で作成済み)の`compute_file_sha256(path) -> str`、`quarantine_row(row, error) -> None`(不正行を隔離しつつ他行を継続処理するコンテキストマネージャ/デコレータ)、`sanitize_formula_cell(value: str) -> str`(Excel数式インジェクション対策、エクスポート側T23で使用)を利用する。CSV列定義は`docs/04_IMPLEMENTATION_AND_TESTS.md`§5(`products.csv`/`product_research.csv`/`shipping_rates.csv`/`fee_profiles.csv`)の列名をそのまま採用し、`exchange_rates.csv`は列 `base_currency,quote_currency,rate,effective_at`(01/03文書のexchange_ratesテーブルに対応、本タスクで列名確定)とする。各importerは`domain/models.py`の対応するPydanticモデル(`ProductInput`/`MarketResearchInput`/`ShippingQuote`/`FeeProfile`)へ変換し、DB書き込みは行わない(Service層の責務)。

## バッチ2(並列実行可能、バッチ1の一部+T05,T06に依存)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T16 | 商品・仕入先Repository | `db/repositories/product_repository.py`, `db/repositories/supplier_repository.py`, `tests/integration/test_product_supplier_repository.py` | T05,T06 | F7,F8,F29 | `uv run pytest tests/integration/test_product_supplier_repository.py -q`(一意制約`uq_products_jan`/`uq_supplier_external`違反時の挙動、upsert、`effective_cost_jpy`保存、最新スナップショット取得インデックス利用) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T17 | Marketデータ Repository | `db/repositories/market_repository.py`, `tests/integration/test_market_repository.py` | T05,T06 | F9,F33 | `uv run pytest tests/integration/test_market_repository.py -q`(`market_queries`/`market_research_metrics`/`ebay_listings`/`ebay_listing_snapshots`のCRUD・一意制約・最新取得) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T18 | Opportunity Repository | `db/repositories/opportunity_repository.py`, `tests/integration/test_opportunity_repository.py` | T05,T06 | F16,F21 | `uv run pytest tests/integration/test_opportunity_repository.py -q`(`opportunity_snapshots`保存、`ix_opportunity_rank`を使うランキングクエリのEXPLAIN確認) | [x] | codex(実装)+リーダー(実DB検証代行・EXPLAIN検証を少数行データでも安定する形に修正) |
| T19 | 参照データRepository | `db/repositories/reference_data_repository.py`, `tests/integration/test_reference_data_repository.py` | T05,T06 | F10 | `uv run pytest tests/integration/test_reference_data_repository.py -q`(`exchange_rates`/`shipping_rates`/`fee_rules`の期間有効性検索) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T20 | 実行・監査Repository | `db/repositories/run_repository.py`, `tests/integration/test_run_repository.py` | T05,T06 | F11,F21,F34 | `uv run pytest tests/integration/test_run_repository.py -q`(`scan_runs`/`import_batches`(ハッシュ一意制約による冪等性)/`audit_logs`) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T21 | Importサービス | `services/import_service.py`, `tests/integration/test_import_service.py` | T12,T13,T14,T15,T16,T17,T19,T20 | F8,F9,F10,F11 | `uv run pytest tests/integration/test_import_service.py -q`(同一CSVを2回取込→`import_batches`/`supplier_price_snapshots`等に重複が作られないことを検証=S9) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T22 | Opportunityサービス | `services/opportunity_service.py`, `tests/integration/test_opportunity_service.py` | T08,T09,T10,T11,T16,T17,T18,T19,T20 | F13〜F21 | `uv run pytest tests/integration/test_opportunity_service.py -q`(3シナリオ計算・スコア・判定をDB保存、同一入力2回実行で結果が同一=S4、`compliance_status=blocked`が必ず`BLOCKED`=S6) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T23 | Reporting/Exportサービス | `services/reporting_service.py`, `exporters/opportunities_csv.py`, `exporters/audit_jsonl.py`, `tests/unit/test_exporters.py`, `tests/integration/test_reporting_service.py` | T18,T20 | F19,F20,F21 | `uv run pytest tests/unit/test_exporters.py tests/integration/test_reporting_service.py -q`(CSV出力の数式インジェクション対策=`=`,`+`,`-`,`@`始まりセルの無害化、コスト内訳合計が`total_cost_jpy`と一致=S12) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T24 | Matchingサービス | `services/matching_service.py`, `tests/unit/test_matching_service.py` | T11,T16,T17 | F27 | `uv run pytest tests/unit/test_matching_service.py -q`(domain/matching.pyをRepositoryの既存候補群に適用する統合ロジック) | [x] | codex |
| T25 | CLI dbコマンド | `cli_commands/db_commands.py`(実装で置換), `tests/integration/test_cli_db_commands.py` | T07,T05 | F7 | `uv run pytest tests/integration/test_cli_db_commands.py -q`(`finder db check/upgrade/current`をTyper `CliRunner`で検証) | [x] | codex(実装)+リーダー(検証・`db current`のCLI実装をalembic内部printからDB直接照会+typer.echoへ修正) |
| T26 | CLI importコマンド | `cli_commands/import_commands.py`(実装で置換), `tests/integration/test_cli_import_commands.py` | T07,T21 | F8,F9,F10,F11 | `uv run pytest tests/integration/test_cli_import_commands.py -q` | [x] | codex(実装)+リーダー(実DB検証代行。`exchange_rates`に存在しない`import_batch_id`列を前提にしたテスト誤りを修正) |
| T27 | CLI calculateコマンド | `cli_commands/calculate_commands.py`(実装で置換), `tests/integration/test_cli_calculate_commands.py` | T07,T22 | F18 | `uv run pytest tests/integration/test_cli_calculate_commands.py -q` | [x] | codex(実装)+リーダー(実DB検証代行) |
| T28 | CLI report/exportコマンド | `cli_commands/report_commands.py`(実装で置換), `tests/integration/test_cli_report_commands.py` | T07,T23 | F19,F20 | `uv run pytest tests/integration/test_cli_report_commands.py -q` | [x] | codex(実装)+リーダー(実DB検証代行) |
| T29 | Phase1 E2Eサンプル | `data/samples/products.csv`, `data/samples/product_research.csv`, `data/samples/shipping_rates.csv`, `data/samples/fee_profiles.csv`, `data/samples/exchange_rates.csv`, `tests/integration/test_e2e_phase1.py` | T25,T26,T27,T28 | F22 / S1,S2,S3,S4,S9,S12 | `uv run pytest tests/integration/test_e2e_phase1.py -q`(`db upgrade`→4種`import`→`calculate opportunities`→`report top`→`export opportunities`が一気通貫でエラーなく完了。BLOCKED商品が`report top`のBUY_TEST系に出ないことを確認) | [x] | codex(実装)+リーダー(実DB検証代行) |

**バッチ2 実装メモ**
- T16〜T20: 各RepositoryはSQLAlchemy 2.x `Session`を受け取るクラス(例: `class ProductRepository: def __init__(self, session: Session): ...`)とし、`get_or_create`/`upsert`/`get_latest_by_*`等のメソッドを提供。DBモデルは全てT04の`db/models.py`を使用(新規定義しない)。
- T21: `import_service.py`は各`importers/*.py`(T12〜T15)の検証結果を受け取り、`ImportBatchRepository`(T20)でSHA-256ハッシュを事前チェックして冪等性を担保し、`ProductRepository`/`SupplierRepository`/`MarketRepository`/`ReferenceDataRepository`へ保存する。不正行はファイル/行単位で隔離しトランザクションは正常行のみコミットする。
- T22: `opportunity_service.py`は`config/candidate_rules.yaml`と`fee_rules`/`shipping_rates`/`exchange_rates`をRepository経由で読み込み、Domain層(T08〜T11)へ明示的に引数として渡す(Domain層はconfigを直接読まない)。Optimistic/Base/Conservativeの3シナリオそれぞれで`calculate_scenario`を呼び出し、`OpportunityRepository`(T18)で`opportunity_snapshots`へ保存する。`input_snapshot`列には計算に使った為替・手数料率・送料表バージョン等を保存する。
- T23: `sanitize_formula_cell`(T04 `csv_common.py`)を必ずCSV出力の全セルに適用する。
- T25〜T28: T07で作成済みのスタブファイルの中身をTyperコマンド実装で置き換える(ファイルは新規作成ではなく既存スタブの完成)。

## バッチ3(並列実行可能、Phase2: 国内API連携)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T30 | 共通APIクライアント基盤 | `clients/base.py`, `tests/contract/test_client_base.py` | T02,T04 | F26 | `uv run pytest tests/contract/test_client_base.py -q`(respxで200/429/5xx/timeoutをモックし、429/5xx限定リトライ+exponential backoff+jitter、400/401/403/404は非リトライを検証。認証ヘッダーがログにマスクされることを検証) | [x] | codex |
| T31 | Yahoo!ショッピングクライアント | `clients/yahoo_shopping.py`, `normalizers/yahoo_normalizer.py`, `tests/contract/test_yahoo_client.py` | T30,T04 | F23,F26 | `uv run pytest tests/contract/test_yahoo_client.py -q`(jan_code優先検索→query検索フォールバック、200/400/401/403/404/429/500系/不正JSON、raw_payload保存、`SupplierOffer`への正規化) | [x] | codex |
| T32 | 楽天API 2クライアント | `clients/rakuten_ichiba.py`, `clients/rakuten_product.py`, `normalizers/rakuten_normalizer.py`, `tests/contract/test_rakuten_client.py` | T30,T04 | F24,F25,F26 | `uv run pytest tests/contract/test_rakuten_client.py -q`(Ichiba Item Search/Product Search双方、200/429/5xx/pagination) | [x] | codex |
| T33 | 国内Marketサービス | `services/market_service.py`, `tests/integration/test_market_service.py` | T31,T32,T11,T16,T17,T20,T24 | F27,F28,F29 | `uv run pytest tests/integration/test_market_service.py -q`(Yahoo/楽天取得結果に`domain/matching.py`を適用、API障害時に既存データでランキング継続=F28、`effective_cost_jpy`(送料込み実質価格)保存=F29) | [x] | codex(実装)+リーダー(実DB検証代行) |
| T34 | CLI fetch(国内)コマンド | `cli_commands/fetch_commands.py`(国内部分を実装で置換), `tests/integration/test_cli_fetch_domestic.py` | T07,T33 | F23,F24,F25,F28 | `uv run pytest tests/integration/test_cli_fetch_domestic.py -q`(`finder fetch domestic --source yahoo/rakuten`、`finder fetch all --stale-only`) | [x] | codex(実装)+リーダー(実DB検証代行) |

**バッチ3 実装メモ**
- T30: `clients/base.py`は`class ApiClient`基底(httpx.Clientラップ)、`tenacity.retry`デコレータで`retry_if_exception_type`に429/5xxのみ対象とするカスタム例外クラス(`RetryableApiError`)を定義し、400/401/403/404は`NonRetryableApiError`として即座に上位へ伝播させる。
- T31/T32: 各クライアントはAPIキーを`config.py`(T02)の`Settings`から取得し、無効化時(`YAHOO_SHOPPING_ENABLED=false`等)は呼び出し前にスキップする。normalizerはAPIレスポンスをPydanticで検証後`SupplierOffer`(T04 `domain/models.py`)へ変換する。
- T33: `market_service.py`は`matching_service.py`(T24)を呼び出してJAN/型番/タイトル類似度でproduct突合し、`SupplierRepository`(T16)へ`supplier_price_snapshots`として保存する。Yahoo/楽天いずれかがtimeout/429/5xxで失敗しても他方の結果と既存DBデータで処理を継続する(例外を握りつぶさずログに記録した上で処理継続)。

## バッチ4(Phase3: eBay Browse API連携)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T35 | eBay OAuth+Browseクライアント | `clients/ebay_auth.py`, `clients/ebay_browse.py`, `tests/contract/test_ebay_client.py` | T30 | F30,F32 | `uv run pytest tests/contract/test_ebay_client.py -q`(Client Credentialsトークン取得・キャッシュ、keyword/GTIN検索、`next`優先pagination、401時トークン再取得1回のみ、403/未承認時は例外`EbayAccessDeniedError`を送出) | [x] | codex |
| T36 | eBay正規化+サービス | `normalizers/ebay_normalizer.py`, `services/ebay_service.py`, `tests/integration/test_ebay_service.py`, `tests/contract/test_ebay_fallback.py` | T35,T17,T11,T16 | F30,F31,F32,F33 | `uv run pytest tests/integration/test_ebay_service.py tests/contract/test_ebay_fallback.py -q`(価格/送料/condition/seller country正規化、外れ値除外後の中央値と競合件数計算、`EbayAccessDeniedError`捕捉時にCSVモード(`ebay_listings`手動CSVまたはProduct Research CSV)へフォールバックしログ・監査ログに記録=S8) | [x] | codex(実装)+リーダー(実DB検証代行。ログ文言"falling back to csv"と"fallback"の単純な文字列不一致テストを修正) |
| T37 | CLI fetch(eBay)+dailyコマンド | `cli_commands/fetch_commands.py`(eBay部分を追記実装), `cli_commands/daily_command.py`(実装で置換), `services/daily_service.py`, `tests/integration/test_cli_daily.py` | T34,T36,T21,T22,T23 | F34 / S8 | `uv run pytest tests/integration/test_cli_daily.py -q`(`finder daily --stale-only --export-dir`が04文書§4の10手順どおりに動作、eBayキー未設定/403でも非0終了せず完了しCSVモードへフォールバックしたことがログから確認できる) | [x] | codex(実装)+リーダー(実DB検証代行。T34作成時は`fetch all`のeBay部分がスタブだったため、T37実装後に`test_cli_fetch_domestic.py`の期待値"not implemented yet"を実際の出力に更新) |

**バッチ4 実装メモ**
- T35: `ebay_auth.py`はClient Credentialsで取得したApplication Access Tokenをプロセス内メモリ(有効期限付き)でキャッシュする。401発生時のみトークン再取得を1回だけ試行し、それでも失敗すれば上位へ例外伝播する(05文書の障害時動作表に準拠)。
- T36: `ebay_service.py`は`EBAY_ENABLED=false`または`EbayAccessDeniedError`捕捉時に、既存の`ebay_listings`手動CSV(products_csvと同様の仕組みで別途importerを都度作らず、`market_research_metrics`/`ebay_listings`の既存データをそのまま利用する設計とする)とProduct Research CSVのみで処理を継続する。中央値計算は四分位範囲(IQR)等でシンプルな外れ値除外を行い、`total`件数を鵜呑みにせず`ebay_listings`保存件数を競合件数として扱う。
- T37: `daily_service.py`が04文書§4の10ステップ(DB接続確認→設定検証→為替更新→古い国内価格更新→eBay更新→Product Research新規CSV取込→機会スナップショット計算→上位候補CSV出力→実行サマリー出力→失敗件数閾値超過時は非0終了)をこの順序で実行するオーケストレーター。`scan_runs`(T20 Repository)に`run_id`を発行し全ステップの結果を紐付ける。

## バッチ5(Phase4: 運用)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T38 | systemdデプロイ設定 | `deploy/systemd/opportunity-finder.service`, `deploy/systemd/opportunity-finder.timer`, `scripts/daily_run.sh` | T07 | F35 | `systemd-analyze verify deploy/systemd/opportunity-finder.service`(利用可能な環境の場合)、無ければ`bash -n scripts/daily_run.sh`で構文チェック | [x] | codex |
| T39 | MySQLバックアップスクリプト | `scripts/backup_mysql.sh`, `scripts/restore_mysql_example.sh` | T02 | F36 | `bash -n scripts/backup_mysql.sh scripts/restore_mysql_example.sh`(構文チェック)、`shellcheck`があれば追加実行 | [x] | codex |
| T40 | CI+secretスキャン | `.github/workflows/ci.yml`, `scripts/check_no_secrets.sh` | T05 | F37 / S10,S13 | GitHub Actions上で`uv sync --frozen && uv run ruff format --check . && uv run ruff check . && uv run alembic upgrade head && uv run pytest -q`が全て成功。`scripts/check_no_secrets.sh`はリポジトリ全体をgrepし`.env`実体・生APIキーらしき文字列が含まれないことを確認するローカル実行可能なスクリプト | [x] | codex(実装)+リーダー(`bash scripts/check_no_secrets.sh`をプロジェクト全体に対して実行し検出なしを確認) |
| T41 | README確定 | `README.md`(全面更新) | T37,T38,T39,T40 | S13(文書要件) | `README.md`に初期設定手順・`.env`設定・`uv run alembic upgrade head`・E2Eサンプル実行手順・systemd導入手順・バックアップ手順が記載されていることを目視確認(自動テストなし、reviewerによるチェックリスト確認) | [x] | リーダー(architect当初方針どおりCodex委譲せず直接作成。参照ファイルの実在も確認済み) |

## 任意(nice-to-have、MVP必須外)

| ID | タスク名 | 担当ファイル | depends_on | 対応要件 | テスト方法 | 状態 | executor |
|----|---------|------------|------------|---------|-----------|------|----------|
| T42 | Streamlit管理画面 | `dashboard/app.py` | T22,T23,T19 | N1 | `uv run streamlit run dashboard/app.py --server.headless true`が起動エラーなく実行できることを目視確認(自動E2Eテストは任意) | [ ] | |

---

## 担当ファイルの重複チェック結果

全42タスクの担当ファイル一覧を突き合わせた結果、以下を除き完全に互いに素(disjoint)である。

- `cli_commands/db_commands.py`(T07で骨子作成→T25で実装完成)、`import_commands.py`(T07→T26)、`calculate_commands.py`(T07→T27)、`report_commands.py`(T07→T28)、`fetch_commands.py`(T07→T34→T37)、`daily_command.py`(T07→T37): いずれも**depends_onで直列関係が保証されており、同一バッチ内で並列実行されることはない**(T07は先行タスクで単独実行、T25〜T28はバッチ2、T34はバッチ3、T37はバッチ4)。
- `README.md`(T01で骨子→T41で全面更新): 同様にT41はT37/T38/T39/T40完了後の最終タスクであり並列衝突しない。

上記6ファイルはいずれも「後続タスクが先行タスクの成果物を引き継いで完成させる」直列依存であり、**同一バッチ内で複数タスクが同時に同一ファイルを編集するケースは存在しない**。それ以外の全ファイル(DBモデル、ドメインロジック、Repository、Service、CSV importer、APIクライアント、テストファイル等)は各タスクに1対1で排他的に割り当てられており、並列実行時の衝突リスクはない。

---

## 置いた仮定(spec.mdのA1〜A4に加え、design.md/tasks.md作成にあたり新たに置いたもの)

- **A5**: `ebay_listings`/`ebay_listing_snapshots`/`exchange_rates`/`shipping_rates`/`fee_rules`/`scan_runs`/`import_batches`/`audit_logs`のDDLは01文書に具体案が無かったため、01文書の型ルール・命名規則に厳密に従い設計書§3.2で新規に確定した。
- **A6**: `domain/models.py`のPydanticクラスの具体的フィールド定義は04文書のクラス名リストのみから、spec.mdのCSV仕様・DDL・計算式と矛盾しないよう設計書§5.2で導出した。
- **A7**: `Money`はドメイン内部計算専用とし、Pydantic境界モデルは`Decimal`を直接使う設計とした。
- **A8**: CLIの`report`/`export`を同一ファイルにまとめる、`fetch_commands.py`をPhase2→Phase3で逐次拡張する、というファイル分割は本書で新規に確定した(直列depends_onで衝突を回避)。
- **A9**: `ebay_listings`の手動CSV入力(eBay APIフォールバック時の現在出品CSV)は、02文書「eBay現在出品の手動CSV」の記述はあるが専用importerファイルの指定が無かったため、専用importerを新規に追加せず`ebay_service.py`(T36)内でCSV読込ロジックを扱う設計とした。運用上CSV列が複雑化する場合は将来的に`importers/ebay_listings_csv.py`として切り出す余地を残す。
