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
