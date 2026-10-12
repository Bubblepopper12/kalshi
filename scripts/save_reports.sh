#!/bin/sh
# Commit research/reports and push to main (used by the Research workflow after each league).
# Usage: scripts/save_reports.sh [what]   e.g. scripts/save_reports.sh NFL
git add research/reports
git diff --cached --quiet && exit 0
git commit -q -m "Research results: ${1:-all} $(date -u +%Y-%m-%d)"
for i in 1 2 3; do
  git pull --rebase -q origin main && git push -q origin HEAD:main && exit 0
  sleep 5
done
exit 1
