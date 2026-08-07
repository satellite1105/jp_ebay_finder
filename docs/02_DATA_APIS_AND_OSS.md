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
