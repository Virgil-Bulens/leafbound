#!/usr/bin/env bash
# Run leafbound on every URL in urls.txt and save EPUBs to conversions/.
# Usage: bash tests/convert_all.sh [--timeout SECONDS]
#
# Paywall URLs (under a "# paywall" section comment) are expected to fail
# and are counted separately, not as errors.

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
paywall_fail=0
total=0
in_paywall=0

while IFS= read -r line || [[ -n "$line" ]]; do
    # Track paywall section
    if [[ "$line" == "# paywall"* ]]; then
        in_paywall=1
    fi

    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue

    total=$((total + 1))
    url="$line"
    echo "[$total] $url"

    output=$(leafbound "$url" --output "$OUTPUT_DIR" --timeout "$TIMEOUT" 2>&1)
    exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        echo "$output"
        pass=$((pass + 1))
    else
        err_msg=$(echo "$output" | grep -i "^error:" | head -1 || true)
        if [[ $in_paywall -eq 1 ]]; then
            echo "  expected failure (paywall): ${err_msg:-no output}"
            paywall_fail=$((paywall_fail + 1))
        else
            echo "  FAILED: ${err_msg:-exit $exit_code}" >&2
            fail=$((fail + 1))
        fi
    fi
    echo
done < "$URLS_FILE"

echo "---"
echo "Results: $pass passed, $fail failed, $paywall_fail expected paywall failures (out of $total URLs)"
echo "EPUBs written to: $OUTPUT_DIR"

[[ $fail -eq 0 ]]
