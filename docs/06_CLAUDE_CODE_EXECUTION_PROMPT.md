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
