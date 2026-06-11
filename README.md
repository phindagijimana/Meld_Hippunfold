# Meld_Hippunfold

Snakemake pipeline that runs **MELD Graph** lesion prediction and **HippUnfold** hippocampal subfield segmentation on the same BIDS T1w, fuses subfields into MELD native space, and computes **lesion asymmetry / concordance statistics** (same analysis as [MELD_CBF](../Meld_CBF/pipeline), on structural T1 instead of CBF).

Driven by the **`./meldhip`** CLI on SLURM (or local dry-run).

## Prerequisites

Sibling checkouts (default layout under `Documents/`):

| Path | Provides |
|------|----------|
| `../Meld_Graph/docker_version/` | `meld-docker`, licenses, models, MELD `.sif` |
| `../HippUnfold/` | `run_hippunfold.sh`, HippUnfold `.sif` |

BIDS input with `sub-*/**/anat/*_T1w.nii.gz` per subject.

## Install

```bash
cd Meld_Hippunfold
cp production.env.example production.env   # optional site paths
./meldhip install
./meldhip check
```

## Quick start

```bash
./meldhip start -i /path/to/bids
./meldhip logs -f                    # tail last SLURM job
./meldhip start -i /path/to/bids -p sub-001 sub-002
./meldhip start -i /path/to/bids --dry-run
./meldhip start -i /path/to/bids --no-analysis-viz   # skip PNG figures
```

## Key outputs (under `work/`)

| Path | Content |
|------|---------|
| `meld_data/output/predictions_reports/<sub>/predictions/prediction.nii.gz` | MELD lesion map |
| `hippunfold/<sub>/anat/` | HippUnfold subfield segmentations |
| `fused/<sub>/hipp_subfields_in_meld_space.nii.gz` | Subfields resampled to MELD grid |
| `meld_data/output/analysis/<sub>/lesion_in_clusters_<sub>.csv` | Per-lesion stats |
| `meld_data/output/cohort_lesion_stats.csv` | Cohort table + concordance call |
| `meld_data/output/analysis/<sub>/figures/*.png` | T1 / lesion / subfield overlays |

## Documentation

- **[USER_GUIDE.md](USER_GUIDE.md)** — pipeline DAG, CLI, config, metrics, troubleshooting
- **[meld.md](meld.md)** — MELD Graph container and `meld-docker` reuse
- **[hip.md](hip.md)** — HippUnfold container and `run_hippunfold.sh` reuse

## Production checklist

| Step | Command |
|------|---------|
| Site paths | Edit `production.env` (optional) |
| Images + venv | `./meldhip install` |
| Preflight | `./meldhip check` |
| Run cohort | `./meldhip start -i <bids>` |
| Monitor | `./meldhip logs -f` / `squeue -u $USER` |
