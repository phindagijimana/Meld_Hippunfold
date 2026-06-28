#!/usr/bin/env bash
# Run meld-docker for one subject. Ensures canonical BIDS bind for any legacy symlinks.
set -euo pipefail

subject="${1:?subject id}"
shift

MELD_DEPLOY_ROOT="${MELD_DEPLOY_ROOT:?MELD_DEPLOY_ROOT not set}"
MELD_DATA_DIR="${MELD_DATA_DIR:?MELD_DATA_DIR not set}"
MELD_DOCKER="${MELD_DEPLOY_ROOT}/meld-docker"

_meld_use_flair() {
  case "${MELD_USE_FLAIR:-0}" in
    1|true|TRUE|yes|Yes|on|ON) return 0 ;;
    0|false|FALSE|False|no|No|off|OFF) return 1 ;;
    *) return 1 ;;
  esac
}

# Remove stale partial FreeSurfer trees from aborted runs (empty mri/ blocks MELD).
fs_out="${MELD_DATA_DIR}/output/fs_outputs/${subject}"
if [[ -d "$fs_out" && ! -f "${fs_out}/mri/T1.mgz" ]]; then
  echo "run_meld_subject: removing incomplete FreeSurfer outputs: ${fs_out}" >&2
  rm -rf "$fs_out"
fi
pred_out="${MELD_DATA_DIR}/output/predictions_reports/${subject}"
if [[ -d "$pred_out" && ! -f "${pred_out}/predictions/prediction.nii.gz" ]]; then
  echo "run_meld_subject: removing incomplete prediction outputs: ${pred_out}" >&2
  rm -rf "$pred_out"
fi

# MELD FAQ: FreeSurfer trees built with FLAIR must be removed before T1-only rerun.
had_flair_fs=0
if ! _meld_use_flair && [[ -f "${fs_out}/mri/FLAIR.mgz" ]]; then
  echo "run_meld_subject: removing FreeSurfer outputs built with FLAIR (MELD_USE_FLAIR=0): ${fs_out}" >&2
  had_flair_fs=1
  rm -rf "$fs_out"
fi
if [[ "$had_flair_fs" -eq 1 ]]; then
  echo "run_meld_subject: removing predictions from prior FLAIR-inclusive run: ${pred_out}" >&2
  rm -rf "$pred_out"
  rm -f "${MELD_DATA_DIR}/.meld_done_${subject}"
fi

if [[ -n "${BIDS_DIR:-}" && -d "${BIDS_DIR}" ]]; then
  bids_bind="$(realpath "${BIDS_DIR}")"
  export APPTAINER_BINDPATH="${bids_bind}:${bids_bind}${APPTAINER_BINDPATH:+,$APPTAINER_BINDPATH}"
  export SINGULARITY_BINDPATH="$APPTAINER_BINDPATH"
fi

exec bash "$MELD_DOCKER" run "$subject" "$@"
