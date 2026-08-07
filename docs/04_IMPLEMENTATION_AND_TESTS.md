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
