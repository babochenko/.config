#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

run_test() {
  local runner="$1" test_file="$2"
  echo ""
  echo "--- Running: $test_file"
  if "$runner" "$test_file"; then
    echo "--- PASSED"
  else
    echo "--- FAILED"
    FAILED=1
  fi
}

run_test ruby "$SCRIPT_DIR/git_review_reply/test.rb"
run_test zsh  "$SCRIPT_DIR/completions/test.zsh"
run_test zsh  "$SCRIPT_DIR/completions/smoke.zsh"

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "=== All test suites passed ==="
else
  echo "=== Some test suites failed ==="
  exit 1
fi
