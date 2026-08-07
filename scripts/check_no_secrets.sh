#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
status=0

report_files() {
  local heading="$1"
  shift
  printf '%s\n' "$heading" >&2
  printf '  %s\n' "$@" >&2
  status=1
}

# A real .env file must never be committed. Examples and samples are allowed.
tracked_env_files=()
if git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  while IFS= read -r -d '' tracked_file; do
    filename="${tracked_file##*/}"
    case "$filename" in
      .env.example|.env.sample)
        ;;
      .env|.env.*)
        tracked_env_files+=("$tracked_file")
        ;;
    esac
  done < <(git -C "$repo_root" ls-files -z -- .)
fi

if ((${#tracked_env_files[@]} > 0)); then
  report_files "Tracked real .env file(s) detected:" "${tracked_env_files[@]}"
fi

# Scan project-authored files. Dependency trees, caches, Git internals, and the
# lockfile are excluded because their hashes and generated content create noise.
scan_files=()
while IFS= read -r -d '' candidate; do
  scan_files+=("$candidate")
done < <(
  find "$repo_root" \
    -type d \( \
      -name .git -o \
      -name .venv -o \
      -name node_modules -o \
      -name .pytest_cache -o \
      -name .ruff_cache -o \
      -name __pycache__ \
    \) -prune -o \
    -type f ! -name uv.lock -print0
)

known_prefix_pattern='(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9-]{10,}|(sk|rk)_live_[A-Za-z0-9]{16,})'
assignment_pattern="(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|secret([_-]?access)?[_-]?key|password|passwd)[[:space:]]*[:=][[:space:]]*(['\"][A-Za-z0-9_./+=-]{32,}['\"]|[A-Za-z0-9_+/=-]{32,}[[:space:]]*$)"
long_token_pattern='(^|[^A-Za-z0-9])[A-Za-z0-9]{48,}([^A-Za-z0-9]|$)'
private_key_pattern='-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE'
private_key_pattern+=' KEY-----'

scan_pattern() {
  local label="$1"
  local pattern="$2"
  local mode="${3:-case-sensitive}"
  local matches=()
  local candidate
  local grep_options=(-I -E -q)

  if [[ "$mode" == "ignore-case" ]]; then
    grep_options+=(-i)
  fi

  for candidate in "${scan_files[@]}"; do
    if grep "${grep_options[@]}" -- "$pattern" "$candidate"; then
      matches+=("${candidate#"$repo_root"/}")
    fi
  done

  if ((${#matches[@]} > 0)); then
    report_files "$label" "${matches[@]}"
  fi
}

scan_pattern "Known API key/token prefix detected in:" "$known_prefix_pattern"
scan_pattern "Raw-looking secret assignment detected in:" "$assignment_pattern" ignore-case
scan_pattern "Long raw-looking alphanumeric token detected in:" "$long_token_pattern"
scan_pattern "Private key material detected in:" "$private_key_pattern"

if ((status != 0)); then
  exit "$status"
fi

printf 'No tracked .env files or raw-looking secrets detected.\n'
