# Japan eBay Opportunity Finder

日本国内の仕入価格と海外(主にeBay)販売データを比較し、送料・手数料・関税・広告費・返品引当まで差し引いた予想純利益を再現可能な決定論的ロジックで計算し、高利益な仕入れ候補をランキングするツールです。感覚ではなくデータで仕入判断を行えるようにすることが目的で、**自動購入・自動出品は行いません**。

詳細な要件定義・技術設計・タスク分割は以下を参照してください。

- 要件定義: [`docs/spec.md`](docs/spec.md)
- 技術設計: [`docs/design.md`](docs/design.md)
- タスク分割・実装進捗: [`docs/tasks.md`](docs/tasks.md)
- 実運用前検証(Phase 5): [`docs/operational_validation.md`](docs/operational_validation.md)
- 実行状態(進捗・課題・再開手順): [`PROJECT_STATE.md`](PROJECT_STATE.md)
- 元となった企画資料一式: [`ALL_IN_ONE_SPEC.md`](ALL_IN_ONE_SPEC.md), [`docs/00_PROJECT_BRIEF.md`](docs/00_PROJECT_BRIEF.md) 〜 [`docs/06_CLAUDE_CODE_EXECUTION_PROMPT.md`](docs/06_CLAUDE_CODE_EXECUTION_PROMPT.md)

## できること(MVP)

- 国内商品CSV・Product Research CSV・送料表CSV・手数料表CSV・為替CSVの取込
- Optimistic / Base / Conservative の3シナリオでの利益計算、損益分岐価格の算出
- 機会スコア・データ信頼度スコアの算出
- `BLOCKED` / `MISSING_DATA` / `STALE_DATA` / `REVIEW_COMPLIANCE` / `LOW_DEMAND` / `LOW_PROFIT` / `WATCH` / `BUY_TEST_1` / `BUY_TEST_2` / `REPLENISH` の優先順位付き判定
- Yahoo!ショッピング・楽天(Ichiba Item Search / Product Search)からの国内価格自動取得
- eBay Browse API(Production access承認済みの場合)からの現在出品取得。未承認・権限不足時は自動的にCSVモード(手動出品CSV・Product Research CSV)へフォールバックし、処理を止めません
- CLI・CSV/JSONLエクスポートによる上位候補の確認
- `finder daily` による日次バッチ実行(systemd timer想定)

## 対象外(やらないこと)

- 商品の自動購入・自動発注、eBayへの自動出品
- eBay Product Researchへの自動ログイン取得・CAPTCHA回避・大量スクレイピング
- 廃止済みのeBay Finding API / Shopping APIの利用、非公開のMarketplace Insights APIを前提とした設計
- 食品・化粧品・医薬品・危険物等のAIによる自動承認・最終規制判定
- 新しいDB(PostgreSQL/DuckDB/Supabase/Elasticsearch)の導入。**既存MySQLのみを使用します**

## 必須環境

- Python 3.11以上
- [uv](https://github.com/astral-sh/uv)
- MySQL 8.0以上(専用DB名は既定 `ebay_opportunity`、環境変数で変更可)

## セットアップ

```bash
uv sync
cp .env.example .env   # MySQL接続情報・APIキーを設定する(.envはGit管理しない)
uv run alembic upgrade head
uv run finder --help
```

`.env` には以下を設定します(値は環境ごとに異なるため `.env.example` を参照):

- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_DATABASE` / `MYSQL_USER` / `MYSQL_PASSWORD`
- `YAHOO_SHOPPING_APP_ID` / `YAHOO_SHOPPING_ENABLED`
- `RAKUTEN_APPLICATION_ID` / `RAKUTEN_AFFILIATE_ID`
- `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` / `EBAY_ENABLED`(eBay Browse APIが利用できない場合は`false`のままでよく、CSVモードで完動する)
- `LOG_LEVEL`

**APIキー・パスワードなどの秘密情報は、ソースコード・ログ・Markdown・DBのいずれにも保存しないでください。**

## 使い方(CLI)

CLI名は `finder` です。

```text
finder db check|upgrade|current
finder import products|product-research|shipping|fees|exchange <path>
finder fetch domestic --source yahoo|rakuten --limit N
finder fetch ebay --query-id N
finder fetch all --stale-only
finder calculate opportunities
finder calculate opportunity --product-id N
finder calculate break-even --product-id N
finder report top --limit N [--decision X]
finder export opportunities <path>
finder export audit <path>
finder daily --stale-only --export-dir <dir>
```

### オフラインでの一連の流れ(外部APIなしで完動する、Mode C)

サンプルCSV(`data/samples/`)を使った一気通貫の例です(`tests/integration/test_e2e_phase1.py` と同じ流れ):

```bash
uv run alembic upgrade head
uv run finder import products data/samples/products.csv
uv run finder import product-research data/samples/product_research.csv
uv run finder import shipping data/samples/shipping_rates.csv
uv run finder import fees data/samples/fee_profiles.csv
uv run finder import exchange data/samples/exchange_rates.csv
uv run finder calculate opportunities
uv run finder report top --limit 10
uv run finder export opportunities out/opportunities.csv
```

### 日次バッチ

```bash
uv run finder daily --stale-only --export-dir out/
```

DB接続確認→設定検証→為替更新→古い国内価格更新→eBay更新(利用可能な場合。未承認・権限不足時はCSVモード・既存DBデータへ自動フォールバックし処理を継続)→Product Research新規CSV取込→機会スナップショット計算→上位候補CSV出力→実行サマリー出力、の順に実行し、失敗件数が閾値を超えた場合のみ非0終了します。

## テスト

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run alembic upgrade head   # テスト用MySQLに対して
uv run pytest -q
uv run pytest --cov=src/opportunity_finder --cov-report=term-missing -q
```

個別実行: `uv run pytest tests/unit -q` / `uv run pytest tests/contract -q` / `uv run pytest tests/integration -q`

### テスト用MySQLの用意

`tests/integration/` はテスト専用の実MySQLに接続します(SQLiteでは代用しません)。ローカルでは例えば:

```bash
docker run --rm -d --name finder-test-mysql \
  -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=finder_test \
  -e MYSQL_USER=finder -e MYSQL_PASSWORD=finder -p 3306:3306 mysql:8.4
export MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_DATABASE=finder_test \
       MYSQL_USER=finder MYSQL_PASSWORD=finder
uv run alembic upgrade head
```

CIでは `.github/workflows/ci.yml` のMySQLサービスコンテナを使用します。

## 運用

- **systemd**: `deploy/systemd/opportunity-finder.service` / `.timer`(日次 06:30 Asia/Tokyo、`RandomizedDelaySec=300`)。`ExecStart`のパス等は実運用環境に合わせて書き換えてください。
- **バックアップ**: `scripts/backup_mysql.sh`(`mysqldump --single-transaction`、gzip圧縮、30日超過分を自動削除)。復元例は `scripts/restore_mysql_example.sh`(誤爆防止の確認プロンプト付き)。
- **CI**: `.github/workflows/ci.yml` でlint・型・テストを自動実行。
- **秘密情報チェック**: `bash scripts/check_no_secrets.sh` でリポジトリ内に `.env` 実体や生のAPIキーらしき文字列が含まれていないかをローカルで確認できます。

## ディレクトリ構成

```text
.
├── pyproject.toml / uv.lock / alembic.ini / .env.example
├── config/              # candidate_rules.yaml 等、判定基準・シナリオ乗数・手数料プロファイル
├── migrations/          # Alembicマイグレーション
├── src/opportunity_finder/
│   ├── cli.py, cli_commands/   # CLI(Typer)
│   ├── config.py, logging_config.py
│   ├── db/               # SQLAlchemyモデル・Repository
│   ├── domain/            # Money/Profit/Scoring/Decisions/Compliance/Matching(外部I/Oなし)
│   ├── clients/           # Yahoo/楽天/eBay APIクライアント
│   ├── normalizers/       # 外部APIレスポンス→内部モデル正規化
│   ├── services/          # ユースケース層
│   ├── importers/         # CSV取込
│   └── exporters/         # CSV/JSONL出力
├── data/samples/         # サンプルCSV(E2Eテストで使用)
├── scripts/              # 日次実行・バックアップ・秘密情報チェック
├── deploy/systemd/       # systemd service/timer
└── tests/{unit,integration,contract,fixtures}/
```

## 開発状況・既知の課題

2026-08-08時点、Phase 0〜Phase 6(基盤・オフラインMVP・国内API連携・eBay Browse API連携・運用・納品)の実装(`docs/tasks.md` T01〜T41、MVP必須範囲すべて)が完了しています。2026-08-09には、MVPの利益計算・判定ロジックを実仕入判断に使える信頼度があるかを検証するPhase 5(実運用前検証)を実施しました。decision taxonomy(10値)自体への変更は行っておらず、既存仕様どおりです。全体テストスイート(`uv run pytest -q`)、`ruff check .`、`ruff format --check .` はいずれも通過しています。テスト件数はプロジェクトの進行に応じて増減するため、最新件数は `uv run pytest -q` の実行結果を確認してください。reviewerによる検証(MVP完了時 total_score 0.97、Phase 5完了時の結果は [`PROJECT_STATE.md`](PROJECT_STATE.md) を参照)。詳細な進捗・実行者記録は [`PROJECT_STATE.md`](PROJECT_STATE.md)、実運用前検証の詳細は [`docs/operational_validation.md`](docs/operational_validation.md) を参照してください。

- **実運用前に必ず確認**: 現在このツールを実仕入判断にそのまま使うことは推奨しません。`config/fee_profiles.example.yaml` 等のサンプル手数料率、`data/samples/shipping_rates.csv` のサンプル送料(実際の日本郵便EMS公式料金と比較して大幅に低い)は、実際の契約条件・配送方法の実料金に置き換える必要があります。詳細は [`docs/operational_validation.md`](docs/operational_validation.md) を参照してください。
- **未解決の設計課題**: `config/candidate_rules.yaml`の`maximum_packed_weight_g`は判定ロジックに未接続です(設定値は存在するが超過時の挙動が一次仕様に定義されていない)。詳細は [`docs/operational_validation.md`](docs/operational_validation.md) を参照してください。
- **任意機能**: Streamlit管理画面(`docs/tasks.md` T42)はMVP必須要件ではないため未実装です。
- **開発環境上の制約(記録)**: 開発に使用したCodexサブエージェントの実行サンドボックスからはローカルMySQL(`127.0.0.1:3306`)へのソケット接続が許可されておらず、DB統合テストの最終実行はリーダー(このリポジトリのオーケストレーター)側で代行しました。本番運用・CI環境ではこの制約はなく、通常どおり `uv run pytest` がDB統合テストを含めて実行できます。
- **手数料・送料・為替のサンプル値**: `config/fee_profiles.example.yaml` 等のサンプル値は実装時点の目安であり、実運用前に各プラットフォームの最新の規約・料率を確認して置き換えてください(`docs/spec.md`「禁止事項」参照)。
