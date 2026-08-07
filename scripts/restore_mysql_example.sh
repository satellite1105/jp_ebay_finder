#!/usr/bin/env bash

set -euo pipefail

# このスクリプトは backup_mysql.sh が作成した gzip 圧縮SQLを、既存の
# MySQLデータベースへ復元するための実行可能な例である。
#
# 使用例:
#   ENV_FILE=/path/to/protected.env \
#     ./scripts/restore_mysql_example.sh /path/to/backup_20260101_030000.sql.gz
#
# または、MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
# MYSQL_DATABASE を環境変数として設定してから実行する。
# MYSQL_PASSWORD は mysql の引数にはせず、MYSQL_PWD 経由でのみ渡す。

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_ENV_FILE="${PROJECT_ROOT}/.env"

load_env_file() {
  local env_file
  local had_mysql_host="${MYSQL_HOST+x}" saved_mysql_host="${MYSQL_HOST-}"
  local had_mysql_port="${MYSQL_PORT+x}" saved_mysql_port="${MYSQL_PORT-}"
  local had_mysql_user="${MYSQL_USER+x}" saved_mysql_user="${MYSQL_USER-}"
  local had_mysql_password="${MYSQL_PASSWORD+x}" saved_mysql_password="${MYSQL_PASSWORD-}"
  local had_mysql_database="${MYSQL_DATABASE+x}" saved_mysql_database="${MYSQL_DATABASE-}"
  local had_backup_file="${BACKUP_FILE+x}" saved_backup_file="${BACKUP_FILE-}"

  if [[ -n "${ENV_FILE:-}" ]]; then
    env_file="${ENV_FILE}"
    if [[ ! -r "${env_file}" ]]; then
      printf 'エラー: ENV_FILE を読み込めません: %s\n' "${env_file}" >&2
      exit 1
    fi
  elif [[ -r "${DEFAULT_ENV_FILE}" ]]; then
    env_file="${DEFAULT_ENV_FILE}"
  else
    return
  fi

  set -a
  # shellcheck disable=SC1090 # 実行時に選択される設定ファイルを読み込むため。
  source "${env_file}"
  set +a

  # 呼び出し元から明示された環境変数は .env の値より優先する。
  if [[ "${had_mysql_host}" == x ]]; then MYSQL_HOST="${saved_mysql_host}"; export MYSQL_HOST; fi
  if [[ "${had_mysql_port}" == x ]]; then MYSQL_PORT="${saved_mysql_port}"; export MYSQL_PORT; fi
  if [[ "${had_mysql_user}" == x ]]; then MYSQL_USER="${saved_mysql_user}"; export MYSQL_USER; fi
  if [[ "${had_mysql_password}" == x ]]; then MYSQL_PASSWORD="${saved_mysql_password}"; export MYSQL_PASSWORD; fi
  if [[ "${had_mysql_database}" == x ]]; then MYSQL_DATABASE="${saved_mysql_database}"; export MYSQL_DATABASE; fi
  if [[ "${had_backup_file}" == x ]]; then BACKUP_FILE="${saved_backup_file}"; export BACKUP_FILE; fi
}

require_variable() {
  local variable_name="$1"

  if [[ -z "${!variable_name:-}" ]]; then
    printf 'エラー: 必須環境変数 %s が設定されていません。\n' "${variable_name}" >&2
    exit 1
  fi
}

load_env_file

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_DATABASE="${MYSQL_DATABASE:-ebay_opportunity}"
BACKUP_FILE="${1:-${BACKUP_FILE:-}}"

require_variable MYSQL_USER
require_variable MYSQL_PASSWORD
require_variable MYSQL_DATABASE

if [[ -z "${BACKUP_FILE}" ]]; then
  printf '使い方: %s /path/to/backup_YYYYmmdd_HHMMSS.sql.gz\n' "$0" >&2
  exit 1
fi

if [[ ! -r "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  printf 'エラー: バックアップファイルを読み込めません: %s\n' "${BACKUP_FILE}" >&2
  exit 1
fi

if [[ ! "${MYSQL_PORT}" =~ ^[0-9]+$ ]] || ((MYSQL_PORT < 1 || MYSQL_PORT > 65535)); then
  printf 'エラー: MYSQL_PORT は 1〜65535 の整数で指定してください: %s\n' "${MYSQL_PORT}" >&2
  exit 1
fi

if ! command -v mysql >/dev/null 2>&1; then
  printf 'エラー: mysql コマンドが見つかりません。MySQLクライアントをインストールしてください。\n' >&2
  exit 1
fi

if ! command -v gzip >/dev/null 2>&1; then
  printf 'エラー: gzip コマンドが見つかりません。\n' >&2
  exit 1
fi

# 壊れたgzipを復元処理へ渡さない。これは読み取り専用の事前検査である。
if ! gzip -t -- "${BACKUP_FILE}"; then
  printf 'エラー: gzipバックアップが破損しています: %s\n' "${BACKUP_FILE}" >&2
  exit 1
fi

printf '復元元: %s\n復元先: %s:%s/%s\n' \
  "${BACKUP_FILE}" "${MYSQL_HOST}" "${MYSQL_PORT}" "${MYSQL_DATABASE}"

# ここから先は復元先DBを上書きし得る。入力が完全に "yes" の場合だけ続行する。
if ! read -r -p "本当に復元しますか? (yes/no): " confirm; then
  printf '\n復元を中止しました（確認入力を読み取れませんでした）。\n' >&2
  exit 1
fi
if [[ "${confirm}" != "yes" ]]; then
  printf '復元を中止しました。\n'
  exit 1
fi

# パスワードをプロセス一覧に見える引数へ含めない。
export MYSQL_PWD="${MYSQL_PASSWORD}"
trap 'unset MYSQL_PWD' EXIT

# pipefail により、展開またはmysql投入のどちらかが失敗すれば非ゼロで終了する。
if ! gzip -dc -- "${BACKUP_FILE}" \
  | mysql \
    --host="${MYSQL_HOST}" \
    --port="${MYSQL_PORT}" \
    --user="${MYSQL_USER}" \
    "${MYSQL_DATABASE}"; then
  printf 'エラー: MySQLデータベースの復元に失敗しました。\n' >&2
  exit 1
fi

printf '復元が完了しました: %s\n' "${MYSQL_DATABASE}"
