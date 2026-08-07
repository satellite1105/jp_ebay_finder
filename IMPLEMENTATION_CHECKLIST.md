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
