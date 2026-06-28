#!/usr/bin/env bash
# Stage BIDS subjects into meld_data/input/ (hardlinks) for meld-docker.
# meld-docker bind-mounts only MELD_DATA_DIR -> /data; external symlinks break inside
# the container. Hardlink/copy keeps T1w/FLAIR under /data/input/.
set -euo pipefail

MELD_DATA="${1:?meld_data_dir}"
BIDS_DIR="${2:?bids_dir}"
COHORT="${3:-from_bids}"
SUBJECTS_FILTER="${4:-}"

# MELD_USE_FLAIR=1 stages FLAIR and allows T1+FLAIR recon-all; default 0 = T1w only.
_meld_use_flair() {
  case "${MELD_USE_FLAIR:-0}" in
    1|true|TRUE|yes|Yes|on|ON) return 0 ;;
    0|false|FALSE|False|no|No|off|OFF) return 1 ;;
    *) return 1 ;;
  esac
}

if [[ ! -d "$BIDS_DIR" ]]; then
  echo "prepare_meld_from_bids: BIDS dir not found: $BIDS_DIR" >&2
  exit 1
fi

BIDS_DIR="$(realpath "$BIDS_DIR")"
COHORT_DIR="${MELD_DATA}/${COHORT}"
INPUT_DIR="${MELD_DATA}/input"
MELD_DEPLOY_ROOT="${MELD_DEPLOY_ROOT:-}"
mkdir -p "$COHORT_DIR" "$INPUT_DIR" "${MELD_DATA}/output" "${MELD_DATA}/logs" "${MELD_DATA}/locks"

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

# BIDS root files required by MELD (meld-docker cohort_install_bids_root_files).
if [[ ! -f "${INPUT_DIR}/dataset_description.json" ]]; then
  cat >"${INPUT_DIR}/dataset_description.json" <<'JSON'
{
    "Name": "MELD Graph Container Dataset",
    "BIDSVersion": "1.6.0",
    "DatasetType": "raw",
    "Authors": ["MELD Research Team"],
    "License": "CC0"
}
JSON
fi

if [[ ! -f "${INPUT_DIR}/meld_bids_config.json" ]] || grep -q '"session"' "${INPUT_DIR}/meld_bids_config.json" 2>/dev/null; then
  cat >"${INPUT_DIR}/meld_bids_config.json" <<'JSON'
{
"T1": {
	"datatype": "anat",
	"suffix": "T1w"
	},
"FLAIR": {
	"datatype": "anat",
	"suffix": "FLAIR"
	}
}
JSON
fi

subject_has_t1w() {
  local sub_dir="$1"
  if [[ -d "${sub_dir}/anat" ]]; then
    compgen -G "${sub_dir}/anat/*T1w.nii.gz" &>/dev/null && return 0
  fi
  local ses
  for ses in "${sub_dir}"/ses-*/anat; do
    [[ -d "$ses" ]] || continue
    compgen -G "${ses}/*T1w.nii.gz" &>/dev/null && return 0
  done
  return 1
}

# Copy or hardlink files into dest (prefer hardlinks on same filesystem).
_stage_files() {
  local src_dir="$1"
  local dst_dir="$2"
  local pattern="$3"
  local f
  shopt -s nullglob
  for f in "${src_dir}"/${pattern}; do
    [[ -e "$f" ]] || continue
    if ! cp -al "$f" "${dst_dir}/" 2>/dev/null; then
      cp -a "$f" "${dst_dir}/"
    fi
  done
  shopt -u nullglob
}

stage_subject() {
  local sub="$1"
  local src="${BIDS_DIR}/${sub}"
  local dst="${INPUT_DIR}/${sub}"
  local cohort_dst="${COHORT_DIR}/${sub}"

  if [[ ! -d "$src" ]]; then
    echo "prepare_meld_from_bids: missing $src" >&2
    return 1
  fi
  if ! subject_has_t1w "$src"; then
    echo "prepare_meld_from_bids: skip ${sub}: no *T1w.nii.gz under anat/ or ses-*/anat/" >&2
    return 1
  fi

  rm -rf "$dst"
  mkdir -p "$dst"

  if [[ -d "${src}/anat" ]]; then
    mkdir -p "${dst}/anat"
    _stage_files "${src}/anat" "${dst}/anat" '*T1w*'
    if _meld_use_flair; then
      _stage_files "${src}/anat" "${dst}/anat" '*FLAIR*'
    fi
  else
    local ses anat ses_name
    for ses in "${src}"/ses-*/; do
      [[ -d "$ses" ]] || continue
      anat="${ses}anat"
      [[ -d "$anat" ]] || continue
      compgen -G "${anat}/*T1w.nii.gz" &>/dev/null || continue
      ses_name="$(basename "$ses")"
      mkdir -p "${dst}/${ses_name}/anat"
      _stage_files "$anat" "${dst}/${ses_name}/anat" '*T1w*'
      if _meld_use_flair; then
        _stage_files "$anat" "${dst}/${ses_name}/anat" '*FLAIR*'
      fi
      break
    done
  fi

  if ! subject_has_t1w "$dst"; then
    echo "prepare_meld_from_bids: failed to stage ${sub} into ${dst}" >&2
    return 1
  fi

  ln -sfn "../input/${sub}" "$cohort_dst"
  echo "prepare_meld_from_bids: staged ${sub} into input/ (hardlink/copy) and ${COHORT}/"
}

if [[ -n "$SUBJECTS_FILTER" ]]; then
  for sub in $SUBJECTS_FILTER; do
    [[ "$sub" == sub-* ]] || sub="sub-${sub}"
    stage_subject "$sub"
  done
else
  for src in "${BIDS_DIR}"/sub-*; do
    [[ -d "$src" ]] || continue
    stage_subject "$(basename "$src")"
  done
fi

flair_mode="T1w only (FLAIR not staged)"
if _meld_use_flair; then
  flair_mode="T1w + FLAIR"
fi

MANIFEST="${MELD_DATA}/.meld_prepare_manifest.json"
{
  echo "{"
  echo "  \"meld_use_flair\": $(_meld_use_flair && echo true || echo false),"
  echo "  \"modality_mode\": \"${flair_mode}\","
  echo "  \"cohort\": \"${COHORT}\","
  echo "  \"bids_dir\": \"${BIDS_DIR}\","
  echo "  \"subjects_filter\": \"${SUBJECTS_FILTER}\""
  echo "}"
} >"$MANIFEST"

echo "prepare_meld_from_bids: staged cohort ${COHORT} (${flair_mode}) under ${MELD_DATA}"
