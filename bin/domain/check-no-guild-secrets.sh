#!/usr/bin/env bash
# Fail closed if tracked files look like they contain guild secrets or test-mode defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

fail=0

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  # Unit fixtures may invent IDs; only scan env templates and root config samples.
  case "$path" in
    tests/*) continue ;;
  esac
  if grep -nE '^(TEST_)?GUILD_ID=[0-9]{5,}' "$path" >/dev/null 2>&1; then
    echo "Tracked file has numeric guild id: $path" >&2
    grep -nE '^(TEST_)?GUILD_ID=[0-9]{5,}' "$path" >&2 || true
    fail=1
  fi
done < <(git ls-files '*.env*' '.env*' '**/.env*' 2>/dev/null || true)

# Broader sweep for TEST_GUILD_ID assignments outside tests/.
while IFS= read -r match; do
  [[ -z "$match" ]] && continue
  path="${match%%:*}"
  case "$path" in
    tests/*) continue ;;
    bot/config.py|bin/test.sh|bin/test-bot.sh) continue ;; # env var names / validation only
  esac
  if [[ "$match" =~ TEST_GUILD_ID=[0-9] ]]; then
    echo "Tracked file embeds TEST_GUILD_ID value: $match" >&2
    fail=1
  fi
done < <(git grep -n 'TEST_GUILD_ID=' -- ':!tests/*' 2>/dev/null || true)

for example in .env.example install/.env.example; do
  if [[ -f "$example" ]] && grep -qE '^ENABLE_TEST_COMMANDS=true' "$example"; then
    echo "$example must not enable test commands by default." >&2
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  echo "Secret/test-mode preflight failed." >&2
  exit 1
fi

echo "OK: no tracked guild secrets or test-mode env defaults"
