#!/usr/bin/env bash
# Usage: step-row.sh "Label" <outcome>   -> one markdown table row for $GITHUB_STEP_SUMMARY
set -euo pipefail
case "${2:-}" in
  success)   icon="✅ passed" ;;
  failure)   icon="❌ failed" ;;
  skipped)   icon="⏭️ skipped" ;;
  cancelled) icon="🚫 cancelled" ;;
  *)         icon="❔ ${2:-unknown}" ;;
esac
printf '| %s | %s |\n' "$1" "$icon"
