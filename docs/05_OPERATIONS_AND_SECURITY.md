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
