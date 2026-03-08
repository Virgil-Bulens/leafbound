#!/usr/bin/env bash
# Run leafbound on every URL in urls.txt and save EPUBs to conversions/.
# Usage: bash tests/convert_all.sh [--timeout SECONDS]
#
# Skips blank lines and comment lines (#).
# Paywall articles may produce thin EPUBs or errors — both are expected.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URLS_FILE="$SCRIPT_DIR/urls.txt"
OUTPUT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/conversions"
TIMEOUT=30

# Parse optional --timeout flag
while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout) TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

pass=0
fail=0
total=0

while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue

    total=$((total + 1))
    url="$line"
    echo "[$total] $url"

    if leafbound "$url" --output "$OUTPUT_DIR" --timeout "$TIMEOUT" 2>&1; then
        pass=$((pass + 1))
    else
        echo "  FAILED (exit $?)" >&2
        fail=$((fail + 1))
    fi
    echo
done < "$URLS_FILE"

echo "---"
echo "Results: $pass passed, $fail failed out of $total URLs"
echo "EPUBs written to: $OUTPUT_DIR"
