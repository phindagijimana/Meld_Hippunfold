#!/usr/bin/env bash
# Link BIDS subjects into meld_data/<cohort>/sub-* for meld-docker cohort sync.
set -euo pipefail

MELD_DATA="${1:?meld_data_dir}"
BIDS_DIR="${2:?bids_dir}"
COHORT="${3:-from_bids}"
SUBJECTS_FILTER="${4:-}"

if [[ ! -d "$BIDS_DIR" ]]; then
  echo "prepare_meld_from_bids: BIDS dir not found: $BIDS_DIR" >&2
  exit 1
fi

COHORT_DIR="${MELD_DATA}/${COHORT}"
MELD_DEPLOY_ROOT="${MELD_DEPLOY_ROOT:-}"
mkdir -p "$COHORT_DIR" "${MELD_DATA}/input" "${MELD_DATA}/output" "${MELD_DATA}/logs" "${MELD_DATA}/locks"

# Seed models/meld_params from deploy bundle on first run (if present).
for asset in models meld_params; do
  dst="${MELD_DATA}/${asset}"
  if [[ ! -d "$dst" ]] || ! compgen -G "${dst}/*" &>/dev/null; then
    for src in "${MELD_DEPLOY_ROOT}/${asset}" "${MELD_DEPLOY_ROOT}/meld_data/${asset}"; do
      if [[ -d "$src" ]] && compgen -G "${src}/*" &>/dev/null; then
        mkdir -p "$dst"
        echo "prepare_meld_from_bids: seeding ${asset} from ${src}"
        cp -a "${src}/." "$dst/"
        break
      fi
    done
  fi
done

link_subject() {
  local sub="$1"
  local src="${BIDS_DIR}/${sub}"
  local dst="${COHORT_DIR}/${sub}"
  if [[ ! -d "$src" ]]; then
    echo "prepare_meld_from_bids: missing $src" >&2
    return 1
  fi
  if [[ -e "$dst" ]]; then
    return 0
  fi
  local rel
  rel="$(realpath --relative-to="$COHORT_DIR" "$src")"
  ln -sfn "$rel" "$dst"
}

if [[ -n "$SUBJECTS_FILTER" ]]; then
  # space-separated sub-XXX
  for sub in $SUBJECTS_FILTER; do
    [[ "$sub" == sub-* ]] || sub="sub-${sub}"
    link_subject "$sub"
  done
else
  for src in "${BIDS_DIR}"/sub-*; do
    [[ -d "$src" ]] || continue
    link_subject "$(basename "$src")"
  done
fi

echo "prepare_meld_from_bids: linked cohort ${COHORT} under ${COHORT_DIR}"
