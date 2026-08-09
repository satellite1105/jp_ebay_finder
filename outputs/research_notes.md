# research_notes.md — Phase 5B 外部前提調査(jp_ebay_finder)

調査日: 2026-08-09
目的: 現在の利益計算・判定ロジックが依拠すべき外部前提(eBay手数料・国際販売関連費用・広告費・為替・国際送料・返品リスク・税関)について、一次情報を優先して事実確認する。

各項目は「主張 / 出典URL / 確認日 / 分類」で記録する。分類は以下の4区分。
- **verified**: 一次情報(公式)で直接確認、または複数の独立した情報源で強く裏付けられている
- **configurable assumption**: 公式に変動・選択の幅がある値。固定の「正解値」ではなく運用側で設定すべき値
- **user/business-specific**: 事業者の契約状況・カテゴリ・地域・戦略により異なり、普遍的な定数にできない
- **unverifiable as universal constant**: 公式な固定値が存在しない、または一次情報から直接確認できなかった

---

## 1. eBay Final Value Fee(標準)

- 主張: 米国eBayの多くのカテゴリで標準FVFは13.6% + 注文ごとの固定額($10以下は$0.30、$10超は$0.40)。カテゴリにより2.5%〜15.3%程度まで幅がある(例: 書籍15.3%、ギター等6.7%)。2025年2月14日付で最大0.35%の引き上げが行われた。
- 出典:
  - https://www.ebay.com/help/fees-billing (公式ヘルプ入口。個別ページは自動フェッチがタイムアウトし本文は未直接確認)
  - https://taxomate.com/blog/ebay-seller-fees (二次情報)
  - https://www.webgility.com/blog/ebay-fees (二次情報)
  - https://www.ebay.com/sellercenter/resources/seller-updates/2025-january/final-value-fee (公式更新告知ページ。自動フェッチがタイムアウトしたためタイトル・URLのみ確認、本文は未直接取得)
- 確認日: 2026-08-09
- 分類: **verified**(複数の独立した二次情報源が一致しており、公式ページのタイトル・URLとも整合するが、eBay公式ページ本文の自動取得は接続タイムアウトのため直接確認はできていない。数値の性質上カテゴリ・時期で変動するため、実運用直前に公式ページで再確認を推奨)

## 2. eBay International Fee(越境販売手数料)

- 主張: 米国seller起点で買い手の配送先または登録国が自国と異なる場合、取引総額に対して追加の「International fee」が課される。公式ヘルプ(export.ebay.com)で仕組み自体(発生条件・計算基礎)は確認できたが、正確なパーセンテージは公式ページ本文に明記されておらず「詳細ページを参照」に留まる。二次情報は1.65%という数値で一致している。
- 出典:
  - https://export.ebay.com/en/fees-regulations-policies/seller-fees/ (公式、直接fetch成功。発生条件・計算基礎は確認したが具体的%は非掲載)
  - https://resellmargin.com/blog/ebay-international-fees-by-region-2026 (二次情報、1.65%)
  - https://www.webgility.com/blog/ebay-fees (二次情報、1.65%)
- 確認日: 2026-08-09
- 分類: **configurable assumption**(仕組みは公式確認済みだが、正確な料率は地域・マーケットプレイスにより変動し、公式一次情報で数値そのものは未確認。1.65%は複数の二次情報が一致する参考値であり「暫定値」として扱うべき)

## 3. eBay Promoted Listings(広告費)

- 主張: Promoted Listings – General(Cost-Per-Sale)は出品者が広告料率を2%〜100%の範囲で自ら設定し、広告経由でクリックされ30日以内に売れた場合のみ課金される。固定の「標準広告費率」は存在しない。
- 出典: https://www.ebay.com/help/selling/ebay-advertising/promoted-listings/general-campaign-strategy?id=4164 (公式、タイトル・URLは検索結果で確認。本文はタイムアウトのため二次情報経由で補完)
- 確認日: 2026-08-09
- 分類: **user/business-specific**(出品者が任意設定するため普遍的な定数化はできない。使うか使わないか自体も任意)

## 4. 為替レートの運用方法

- 主張: 国際的な公式固定レートは存在しない。実務上はmid-market rateを基準にし、決済業者・カードブランドのスプレッド(実務上1〜3%程度と言われる)が乗る。多くのガイドは「相場変動を前提に事業計画を立てる」ことを推奨するのみで、万人に共通する固定値・固定運用方法は提示していない。
- 出典:
  - https://stripe.com/resources/more/exchange-rate-risks-for-cross-border-ecommerce-japan
  - https://www.xe.com/blog/business/fx-in-e-commerce-multi-currency-pricing-and-payouts/
- 確認日: 2026-08-09
- 分類: **unverifiable as universal constant**(公式固定値は存在しない。運用ポリシー — 例: 取得日時点レート使用/更新頻度 — は事業者が決める設計判断)

## 5. 国際送料(日本→海外)

- 主張: 日本郵便EMSの公式レート表(2026年時点)で、米国向け(第4地帯)は 0.5kg: ¥3,900 / 1kg: ¥5,300 / 2kg: ¥7,900 / 5kg: ¥15,100。地帯(ゾーン)・重量帯で変動する公式の一次情報が存在する。
- 出典: https://www.post.japanpost.jp/send/oversea/charge/list-ems/all_en.html (日本郵便公式、直接fetch成功)
- 確認日: 2026-08-09
- 分類: **verified**(日本郵便公式サイトから直接確認。ただし発効日はページ上に明記なし、将来の改定に注意。EMS以外の配送手段(国際eパケット等)やフォワーダー利用時は別料金体系である点に留意)

## 6. 返品率・返品引当

- 主張: eBayのカテゴリ別return rateはコミュニティ・業界情報では概ね5〜8%程度(靴等は二桁もあり得る)とされるが、eBay公式が普遍的な「標準返品率」や「返品引当率」を数値で定義している一次情報は見つからなかった。Service Metricsでの返品率監視は存在するが、具体的な閾値は出品者ごとのSeller Dashboardに依存する。
- 出典: https://community.ebay.com/t5/Shipping/Good-Return-Rate/td-p/27732556 (コミュニティ、非公式)
- 確認日: 2026-08-09
- 分類: **unverifiable as universal constant**(公式固定値なし。カテゴリ・商品・季節で大きく変動するため、返品リスクをツールが「事実」として一律計算するのは不適切。ユーザー入力または保守的な感度分析用パラメータとして扱うべき)

## 7. 税・関税

- 主張: eBayの国際取引では、関税・輸入税・通関手数料は基本的に買い手(輸入者)の責任として扱われる。国・注文額・出品者のステータスによって、購入時に前払いされる場合と到着時に買い手が別途支払う場合がある(Import Charges表示の有無等)。日本からの出荷でSpeedPak等一部の配送方法は事前関税払いに対応する場合があるが、一般化はできない。
- 出典: https://www.ebay.com/help/buying/shipping-delivery/buying-authenticity-guarantee-items-japan?id=5453 、コミュニティ複数スレッド
- 確認日: 2026-08-09
- 分類: **user/business-specific**(輸出者=本ツールの利用者が自動計算すべき範囲ではなく、buyer側の税務・通関に依存。ツールが関税額を確定計算することは越権であり、「人間確認が必要」と明示すべき領域)

---

## fact-checker検証結果(独立検証、general-purposeエージェントがfact-checker.md手順に従い実施)

環境上の制約により、専用`fact-checker`サブエージェントはこのセッションで直接呼び出せなかった(`Agent type 'fact-checker' not found`)。同一の手順(fact-checker.md)を`general-purpose`エージェントに厳密に指示して代替実施した。

- claims_checked: 6, overall_reliability: **0.92**
- **verified**(5件): eBay標準FVF 13.6%+$0.30/$0.40(https://www.ebay.com/help/selling/fees-credits-invoices/selling-fees?id=4822)/ 2025-02-14の最大0.35%改定(https://channelx.world/2025/02/ebay-com-final-value-fees-increase-0-35/)/ Promoted Listings General(CPS)の広告料率2%〜100%任意設定(https://export.ebay.com/en/services-tools/advertising/general-campaign-strategy/)/ 日本郵便EMS米国向け(第4地帯)0.5kg ¥3,900・1kg ¥5,300・2kg ¥7,900・5kg ¥15,100(https://www.post.japanpost.jp/send/oversea/charge/list-ems/zone4.html)/ eBayに公式の単一返品率・返品引当定数は存在しない(カテゴリ・出品者ごとにService Metricsで変動)/ 関税・輸入税は基本的に買い手(輸入者)責任、収受方法(前払い vs 到着時)はプログラム次第(https://www.ebay.com/help/selling/fees-credits-invoices/taxes-import-charges?id=4121)。
- **contradicted**: 0件。
- **unverifiable**(1件): International Fee ≈1.65%という数値。公式一次情報(export.ebay.com)は仕組み・計算基礎は確認できるが具体的%は明記していない。複数の独立したeBayコミュニティスレッドが実際に課金された1.65%を報告しており二次情報としての一致度は高いが、公式一次情報で数値そのものは確認できないため「普遍定数として検証済み」とは扱わない。

この結果を受け、上記「2. eBay International Fee」の分類は据え置き(**configurable assumption**、1.65%は参考値であり実運用直前に出品者アカウントの実請求で確認すべき)。他の項目は上記verifiedにより裏付けが強化された。

## 収集時の制約・留保

- eBay公式ヘルプページ本体(ebay.com/help/... , sellercenter/...)への直接WebFetchは複数回タイムアウトした(ボット対策と思われる)。公式URLの存在・タイトル・検索結果スニペットは確認できたが、本文の一次情報直接確認ができなかった項目がある(#1, #3)。これらはfact-checkerによる独立検証、または実運用前にユーザー自身が公式ページを目視確認することを推奨する。
- 「2026年」を含む検索結果には、SEOブログが将来年号を冠して恒常的に更新しているだけの記事が多く含まれる可能性がある。数値が複数の独立ソースで一致する場合のみ参考値として採用し、単一ソースの数値は不採用とした。
