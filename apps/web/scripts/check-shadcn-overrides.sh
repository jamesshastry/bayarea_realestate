#!/usr/bin/env bash
#
# CI gate: lists every place outside `src/components/ui/` that calls `cn(`
# overriding shadcn primitive classNames (per docs/design.md §10.7.4.1).
#
# Each hit must carry an explicit
#
#   /* shadcn-override: <reason> */
#
# magic comment on the line above. Reviewers MUST justify each in PR review.
#
# Exit codes:
#   0 — no unjustified overrides
#   1 — at least one unjustified override (or no shadcn primitives yet, in
#        which case the message is informational; switch to `exit 0` below
#        once the components/ui/ primitives are real shadcn copies and not
#        Phase 2 stubs).
#
# Run from the repo root:
#   bash apps/web/scripts/check-shadcn-overrides.sh

set -euo pipefail

SRC_DIR="apps/web/src"
ALLOWED_DIR="${SRC_DIR}/components/ui"

if [ ! -d "$SRC_DIR" ]; then
  echo "warn: ${SRC_DIR} not found — skipping check (run from repo root)."
  exit 0
fi

# Find all `cn(` references in src outside components/ui, preceded by NO magic
# comment. -A 0 -B 1 lets us inspect the line above each hit.
hits=$(grep -rEn --include='*.ts' --include='*.tsx' \
  -B 1 'cn\(' "$SRC_DIR" \
  | grep -v "$ALLOWED_DIR" \
  | grep -v 'shadcn-override:' \
  || true)

if [ -z "$hits" ]; then
  echo "ok: no unjustified cn() overrides outside components/ui/."
  exit 0
fi

echo "Unjustified cn() overrides outside components/ui/:"
echo "$hits"
echo
echo "Each line above must carry a /* shadcn-override: <reason> */ magic"
echo "comment per docs/design.md §10.7.4.1, OR be moved into components/ui/."
exit 1
