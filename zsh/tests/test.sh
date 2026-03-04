#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

run_test() {
  local test_file="$1"
  echo ""
  echo "--- Running: $test_file"
  if ruby "$test_file"; then
    echo "--- PASSED"
  else
    echo "--- FAILED"
    FAILED=1
  fi
}

run_test "$SCRIPT_DIR/gradle_checkstyle/test.rb"
run_test "$SCRIPT_DIR/git_review_reply/test.rb"

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "=== All test suites passed ==="
else
  echo "=== Some test suites failed ==="
  exit 1
fi
