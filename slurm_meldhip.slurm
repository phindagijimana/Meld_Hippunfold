#!/bin/bash
#SBATCH -J meldhip
#SBATCH -o meldhip_%j.out
#SBATCH -e meldhip_%j.err
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#
# Submitted by ./meldhip start — reads .meldhip/run_config.env

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-.}"
ROOT="$(pwd)"

RUN_CONFIG="$ROOT/.meldhip/run_config.env"
[[ -f "$RUN_CONFIG" ]] || { echo "missing $RUN_CONFIG — run ./meldhip start first" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
source "$RUN_CONFIG"
set +a

if [[ -f "$ROOT/production.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/production.env"
  set +a
fi

export TMPDIR="${TMPDIR:-$HOME/apptainer_tmp}"
mkdir -p "$TMPDIR" "$HIPPUNFOLD_CACHE_DIR" "$WORK_DIR"
export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-$TMPDIR}"
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$HOME/.cache/apptainer}"
export SINGULARITY_BINDPATH="${BIDS_DIR}:${BIDS_DIR},${WORK_DIR}:${WORK_DIR},${HIPPUNFOLD_CACHE_DIR}:${HIPPUNFOLD_CACHE_DIR},${MELD_DATA_DIR}:${MELD_DATA_DIR}"
export APPTAINER_BINDPATH="$SINGULARITY_BINDPATH"
export PYTHONNOUSERSITE=1
unset PYTHONPATH 2>/dev/null || true

VENV="$ROOT/.meldhip/venv"
[[ -f "$VENV/bin/activate" ]] || { echo "venv missing — run ./meldhip install on login node" >&2; exit 1; }
# shellcheck source=/dev/null
source "$VENV/bin/activate"

# subjects list for Snakemake --config
subj_list="[]"
if [[ -n "${SUBJECTS_FILTER:-}" ]]; then
  subj_list="["
  first=1
  for s in $SUBJECTS_FILTER; do
    [[ "$s" == sub-* ]] || s="sub-$s"
    [[ "$first" -eq 1 ]] || subj_list+=", "
    subj_list+="'$s'"
    first=0
  done
  subj_list+="]"
fi

SM_LOG="${WORK_DIR}/snakemake_${SLURM_JOB_ID:-local}.log"

snakemake \
  -s "$ROOT/workflow/Snakefile" \
  --configfile "$ROOT/config/config.yaml" \
  --config \
    "bids_dir=${BIDS_DIR}" \
    "meld_data_dir=${MELD_DATA_DIR}" \
    "hippunfold_out_dir=${HIPPUNFOLD_OUT_DIR}" \
    "fused_dir=${FUSED_DIR}" \
    "meld_deploy_root=${MELD_DEPLOY_ROOT}" \
    "hippunfold_root=${HIPPUNFOLD_ROOT}" \
    "subjects=${subj_list}" \
    "meld_extra_flags=${MELD_EXTRA_FLAGS:-}" \
    "hippunfold_extra_flags=${HIPP_EXTRA_FLAGS:-}" \
    "enable_analysis_viz=${ENABLE_ANALYSIS_VIZ:-true}" \
    "snakemake_cores=${SLURM_CPUS_PER_TASK:-8}" \
  --cores "${SLURM_CPUS_PER_TASK:-8}" \
  --resources heavy_fs=1 hippunfold=2 \
  --reason \
  --latency-wait "${SNAKEMAKE_LATENCY_WAIT:-60}" \
  --keep-going \
  2>&1 | tee "$SM_LOG"
