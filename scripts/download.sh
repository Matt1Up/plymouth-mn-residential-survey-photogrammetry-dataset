#!/usr/bin/env bash
# Download the Thirteen Missions Over Plymouth dataset from Hugging Face.
#   ./scripts/download.sh --images     the 1,421 images, file by file (resumable)
#   ./scripts/download.sh --zip        the same images as one ZIP
#   ./scripts/download.sh --poses      camera poses and tie points
#   ./scripts/download.sh --all        everything (the images twice: loose and in the ZIP)
set -euo pipefail
HF_REPO="${HF_REPO:-Matt1up/plymouth-mn-residential-survey-photogrammetry}"
DEST="${DEST:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/data}"

modes=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --images|--zip|--poses|--all) modes+=("${1#--}"); shift ;;
    --dest)   DEST="$2"; shift 2 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ ${#modes[@]} -eq 0 ]] && { sed -n '2,6p' "$0"; exit 2; }

if ! command -v hf >/dev/null 2>&1 && ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "Needs the Hugging Face CLI:  pip install -U huggingface_hub"
  echo "Or download files in a browser: https://huggingface.co/datasets/$HF_REPO/tree/main"
  exit 1
fi
HF=$(command -v hf || command -v huggingface-cli)

mkdir -p "$DEST"
args=(download "$HF_REPO" --repo-type dataset --local-dir "$DEST")
for m in "${modes[@]}"; do
  case "$m" in
    all)    : ;;
    images) args+=(--include "survey/images/*") ;;
    zip)    args+=(--include "zip/*") ;;
    poses)  args+=(--include "survey/poses/*") ;;
  esac
done

echo "→ $HF_REPO (${modes[*]}) → $DEST"
"$HF" "${args[@]}" || {
  echo
  echo "Stopped early. Run the same command again — finished files are skipped."
  echo "HTTP 429 is Hugging Face's rate limit: wait five minutes, or log in first with  hf auth login"
  exit 1
}
echo
echo "Done. Verify with:  ./scripts/verify.sh"
