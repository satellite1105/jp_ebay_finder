#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_ENV_FILE="${PROJECT_ROOT}/.env"

# ENV_FILE が明示されていればそのファイルを、そうでなければプロジェクト直下の
# .env（存在する場合）を読み込む。.env は Bash で読み込める KEY=VALUE 形式を想定する。
load_env_file() {
  local env_file
  local had_mysql_host="${MYSQL_HOST+x}" saved_mysql_host="${MYSQL_HOST-}"
  local had_mysql_port="${MYSQL_PORT+x}" saved_mysql_port="${MYSQL_PORT-}"
  local had_mysql_user="${MYSQL_USER+x}" saved_mysql_user="${MYSQL_USER-}"
  local had_mysql_password="${MYSQL_PASSWORD+x}" saved_mysql_password="${MYSQL_PASSWORD-}"
  local had_mysql_database="${MYSQL_DATABASE+x}" saved_mysql_database="${MYSQL_DATABASE-}"
  local had_backup_dir="${BACKUP_DIR+x}" saved_backup_dir="${BACKUP_DIR-}"

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
  if [[ "${had_backup_dir}" == x ]]; then BACKUP_DIR="${saved_backup_dir}"; export BACKUP_DIR; fi
}

require_variable() {
  local variable_name="$1"

  if [[ -z "${!variable_name:-}" ]]; then
    printf 'エラー: 必須環境変数 %s が設定されていません。\n' "${variable_name}" >&2
    exit 1
  fi
}

load_env_file

# 接続先と保存先には運用しやすい既定値を設ける。認証情報は必須とし、
# スクリプト内には値を持たせない。
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_DATABASE="${MYSQL_DATABASE:-ebay_opportunity}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/opportunity-finder}"

require_variable MYSQL_USER
require_variable MYSQL_PASSWORD
require_variable MYSQL_DATABASE

if [[ ! "${MYSQL_PORT}" =~ ^[0-9]+$ ]] || ((MYSQL_PORT < 1 || MYSQL_PORT > 65535)); then
  printf 'エラー: MYSQL_PORT は 1〜65535 の整数で指定してください: %s\n' "${MYSQL_PORT}" >&2
  exit 1
fi

if ! command -v mysqldump >/dev/null 2>&1; then
  printf 'エラー: mysqldump コマンドが見つかりません。MySQLクライアントをインストールしてください。\n' >&2
  exit 1
fi

if ! command -v gzip >/dev/null 2>&1; then
  printf 'エラー: gzip コマンドが見つかりません。\n' >&2
  exit 1
fi

mkdir -p -- "${BACKUP_DIR}"

timestamp="$(date +%Y%m%d_%H%M%S)"
backup_file="${BACKUP_DIR}/backup_${timestamp}.sql.gz"
temporary_file="${backup_file}.partial"

# パスワードはコマンドライン引数に含めず、子プロセスの環境だけに渡す。
export MYSQL_PWD="${MYSQL_PASSWORD}"

cleanup() {
  local exit_code=$?

  unset MYSQL_PWD
  if ((exit_code != 0)); then
    rm -f -- "${temporary_file}"
  fi
}
trap cleanup EXIT

if ! mysqldump \
  --host="${MYSQL_HOST}" \
  --port="${MYSQL_PORT}" \
  --user="${MYSQL_USER}" \
  --single-transaction \
  --routines \
  --triggers \
  "${MYSQL_DATABASE}" \
  | gzip -9 >"${temporary_file}"; then
  printf 'エラー: MySQLバックアップの作成に失敗しました。\n' >&2
  exit 1
fi

mv -- "${temporary_file}" "${backup_file}"

# 完成したバックアップがある場合に限り、30日を超えた同形式のファイルを削除する。
find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'backup_*.sql.gz' -mtime +30 -delete

printf 'バックアップを作成しました: %s\n' "${backup_file}"
