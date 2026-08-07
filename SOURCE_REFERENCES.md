# 調査ソース一覧

基準日: 2026-08-06

実装時は必ず公式ドキュメントを再確認すること。API仕様、料金、利用条件は変更される。

## MySQL

- MySQL 8.4 Reference Manual — JSON_VALUE and expression indexes  
  https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html
- MySQL 8.4 Reference Manual — Indexes on Generated Columns  
  https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html
- MySQL 8.4 Reference Manual — Multiple-Column Indexes  
  https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html

## eBay

- Browse API overview  
  https://developer.ebay.com/api-docs/buy/browse/overview.html
- Browse API search method  
  https://developer.ebay.com/api-docs/buy/browse/resources/item_summary/methods/search
- Product Research  
  https://www.ebay.com/help/selling/selling-tools/product-research?id=4853
- Marketplace Insights API overview  
  https://developer.ebay.com/api-docs/buy/marketplace-insights/overview.html
- Buy APIs production eligibility / approval  
  https://developer.ebay.com/api-docs/static/gs_ebay-rest-getting-started-landing.html
- eBay API deprecation status  
  https://developer.ebay.com/develop/get-started/api-deprecation-status
- Finding API decommission notice  
  https://developer.ebay.com/develop/apis/deprecated
- Official eBay OAuth Python client repository  
  https://github.com/eBay/ebay-oauth-python-client
- Archived unofficial Browse API Python client（採用しない）  
  https://github.com/AverHLV/browseapi

## Yahoo!ショッピング

- Yahoo!デベロッパーネットワーク ショッピング商品検索 v3  
  https://developer.yahoo.co.jp/webapi/shopping/shopping/v3/itemsearch.html

## 楽天

- 楽天市場商品検索API  
  https://webservice.rakuten.co.jp/documentation/ichiba-item-search
- 楽天製品検索API  
  https://webservice.rakuten.co.jp/documentation/ichiba-product-search

## Python / OSS

- SQLAlchemy  
  https://github.com/sqlalchemy/sqlalchemy
- Alembic  
  https://github.com/sqlalchemy/alembic
- HTTPX  
  https://github.com/encode/httpx
- Pydantic  
  https://github.com/pydantic/pydantic
- Pydantic Settings  
  https://github.com/pydantic/pydantic-settings
- Tenacity  
  https://github.com/jd/tenacity
- RapidFuzz  
  https://github.com/rapidfuzz/RapidFuzz
- Typer  
  https://github.com/fastapi/typer
- Rich  
  https://github.com/Textualize/rich
- Streamlit  
  https://github.com/streamlit/streamlit
- uv  
  https://github.com/astral-sh/uv
- Ruff  
  https://github.com/astral-sh/ruff
- pytest  
  https://github.com/pytest-dev/pytest

## 採用上の注意

- GitHubのstar数だけで採用しない
- 最終リリース、コミット頻度、Issue、Python対応版を確認する
- 公式SDKでも対象Pythonが古い場合は採用しない
- 非公式eBayスクレイパーは更新停止・規約違反・HTML変更リスクが高いため中核へ使わない
- 依存パッケージは最小限にし、ロックファイルをコミットする
