#!/usr/bin/env bash
# Verify downloaded files against the published SHA-256 lists (every *.sha256 under manifest/).
# Only checks files you actually have, so partial downloads verify fine.
#
#   ./scripts/verify.sh                      files fetched with download.sh / hf download (DEST=./data)
#   ./scripts/verify.sh --unzipped <folder>  the folder the ZIP unpacks to: every image in it is
#                                            checked against the per-image list
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEST:-$ROOT/data}"
UNZIPPED=""
[[ "${1:-}" == "--unzipped" ]] && { UNZIPPED="${2:?--unzipped needs the folder}"; }

[[ -n "$(find "$ROOT/manifest" -name '*.sha256' 2>/dev/null)" ]] || { echo "no checksum lists under $ROOT/manifest" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then sha=(sha256sum); else sha=(shasum -a 256); fi

if [[ -n "$UNZIPPED" ]]; then
  [[ -d "$UNZIPPED" ]] || { echo "no folder at $UNZIPPED" >&2; exit 1; }
  list() { sed -E 's#^([0-9a-f]{64})  [^ ]*/images/#\1  #' "$ROOT/manifest/survey/checksums.sha256"; }
  cd "$UNZIPPED"
else
  [[ -d "$DEST" ]] || { echo "nothing downloaded at $DEST" >&2; exit 1; }
  list() { find "$ROOT/manifest" -name '*.sha256' -exec cat {} +; }
  cd "$DEST"
fi

present=0; ok=0; bad=0; missing=0
while read -r sum path; do
  [[ -z "${sum:-}" ]] && continue
  if [[ -f "$path" ]]; then
    present=$((present+1))
    if [[ "$("${sha[@]}" "$path" | cut -d' ' -f1)" == "$sum" ]]; then ok=$((ok+1))
    else bad=$((bad+1)); echo "CORRUPT: $path"; fi
  else missing=$((missing+1)); fi
done < <(list)

total=$((present+missing))
echo
echo "checked $present of $total files"
echo "  ok        $ok"
echo "  corrupt   $bad"
echo "  absent    $missing  (not downloaded — fine for a partial fetch)"
[[ $bad -eq 0 ]] || { echo; echo "Re-download the corrupt files listed above."; exit 1; }
echo "All present files verified."
