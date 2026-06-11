# Meld_Hippunfold — User Guide

Detailed reference for this pipeline. For install and a quick start, see [README.md](README.md).

## Pipeline overview

MELD and HippUnfold run **in parallel** on the same BIDS dataset. After both finish, HippUnfold subfield labels are resampled onto the MELD `prediction.nii.gz` grid. Lesion statistics reuse the MELD_CBF analysis engine with MELD `T1.mgz` as the scalar map (no CBF registration step).

```
BIDS T1w
    │
    ├─ meld_prepare ── meld_predict ──┬─ fuse_to_meld_space ─┬─ lesion_stats ─┬─ lesion_visualize (optional)
    │                                 │                      │                └─ lesion_aggregate
    └─ hippunfold_predict ────────────┘                      └──────────────────┘
```

### Why fusion is a separate step

MELD and HippUnfold each produce outputs in their own native spaces. This pipeline does **not** register MELD and HippUnfold to each other directly; instead, `fuse_hippunfold_to_meld.py` resamples HippUnfold `*desc-subfields_dseg.nii.gz` (T1w space) onto the MELD prediction NIfTI grid with nearest-neighbour interpolation (`order=0`).

## Architecture

```
Meld_Hippunfold/
├── meldhip                    CLI (install, start, check, logs)
├── slurm_meldhip.slurm        SLURM driver (submitted by start)
├── config/config.yaml         Snakemake defaults + analysis thresholds
├── production.env             optional site overrides (not in git)
├── workflow/
│   ├── Snakefile              full DAG
│   ├── scripts/               BIDS staging, fusion, cohort aggregate
│   └── analysis/              lesion_stats.py, lesion_visualize.py
├── meld.md                    MELD container / meld-docker notes
└── hip.md                     HippUnfold container / run_hippunfold notes
```

Upstream containers are **not rebuilt** here. The pipeline binds into existing lab deployments:

- **MELD:** `../Meld_Graph/docker_version/meld-docker` + `meld_graph_*.sif`
- **HippUnfold:** `../HippUnfold/run_hippunfold.sh` + `khanlab_hippunfold_*.sif`

Host Python (venv via `./meldhip install`): Snakemake, nibabel, pandas, nilearn, matplotlib.

## Work directory layout

After a run with `work_dir=work` (default):

```
work/
├── meld_data/
│   ├── input/<sub>/T1/…              staged from BIDS
│   └── output/
│       ├── fs_outputs/<sub>/mri/
│       │   ├── T1.mgz
│       │   └── aparc+aseg.mgz
│       ├── predictions_reports/<sub>/predictions/prediction.nii.gz
│       ├── analysis/<sub>/
│       │   ├── lesion_in_clusters_<sub>.csv
│       │   └── figures/*.png
│       └── cohort_lesion_stats.csv
├── hippunfold/<sub>/anat/            HippUnfold BIDS derivatives
└── fused/<sub>/
    ├── hipp_subfields_in_meld_space.nii.gz
    └── fusion_manifest.json
```

## CLI reference (`./meldhip`)

```bash
./meldhip install              # pull SIFs (if missing) + create .meldhip/venv
./meldhip check                # images, licenses, meld_data assets, venv, last BIDS
./meldhip start -i <bids>      # write .meldhip/run_config.env + sbatch SLURM job
./meldhip logs [-f] [JOB_ID]   # tail meldhip_*.out/err and snakemake log
./meldhip help
```

### `start` options

| Flag | Meaning |
|------|---------|
| `-i, --bids DIR` | BIDS root (**required**) |
| `-w, --work-dir DIR` | Output root (default: `./work`) |
| `-p, --participant …` | One or more subjects (`sub-` optional); default = all `sub-*` in BIDS |
| `--meld-flags STR` | Extra args to `meld-docker run` |
| `--hipp-flags STR` | Extra args to HippUnfold |
| `--no-analysis-viz` | Run stats + cohort CSV; skip overlay PNGs |
| `--dry-run` | Local `snakemake -n` (no SLURM submit) |

### Environment variables

Set in `production.env` or the shell; `./meldhip start` writes runtime paths to `.meldhip/run_config.env`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `MELD_DEPLOY_ROOT` | `../Meld_Graph/docker_version` | `meld-docker` bundle |
| `HIPPUNFOLD_ROOT` | `../HippUnfold` | `run_hippunfold.sh` |
| `MELD_IMAGE_TAG` | `v2.2.4` | MELD SIF tag for install |
| `HIPPUNFOLD_IMAGE_TAG` | `latest` | HippUnfold SIF tag |
| `HIPPUNFOLD_CACHE_DIR` | `$SCRATCH/hippunfold_cache` | nnU-Net model cache |
| `MELD_CONTAINER_IMAGE` | (from install) | Override MELD SIF path |
| `HIPPUNFOLD_SIF` | (from install) | Override HippUnfold SIF path |
| `SNAKEMAKE_LATENCY_WAIT` | `60` | NFS latency for Snakemake |
| `ENABLE_ANALYSIS_VIZ` | `true` | Set `false` via `--no-analysis-viz` |

## Configuration (`config/config.yaml`)

Edited directly or overridden at runtime via `./meldhip start` / `slurm_meldhip.slurm`.

### Paths and cohort

| Key | Default | Notes |
|-----|---------|-------|
| `meld_deploy_root` | `../Meld_Graph/docker_version` | |
| `hippunfold_root` | `../HippUnfold` | |
| `meld_data_dir` | `work/meld_data` | MELD working tree |
| `hippunfold_out_dir` | `work/hippunfold` | |
| `fused_dir` | `work/fused` | |
| `meld_cohort` | `from_bids` | Passed to `prepare_meld_from_bids.sh` |
| `subjects` | `[]` | Empty = all subjects in BIDS |

### HippUnfold options

| Key | Default |
|-----|---------|
| `hippunfold_modality` | `T1w` |
| `hippunfold_output_spaces` | `T1w` (required for fusion) |
| `hippunfold_extra_flags` | `""` |

### Resources

| Key | Default | Snakemake resource |
|-----|---------|-------------------|
| `snakemake_cores` | `8` | `--cores` |
| `resource_heavy_fs` | `1` | MELD / FreeSurfer jobs |
| `resource_hippunfold` | `2` | HippUnfold jobs |

### Lesion analysis (from MELD_CBF)

| Key | Default | Purpose |
|-----|---------|---------|
| `enable_analysis_viz` | `true` | Generate PNG overlays |
| `hypo_z` | `-1.5` | Voxelwise GM z threshold for `frac_hypo` / `dice_hypo` |
| `asym_concordance_pct` | `-8.0` | ROI asymmetry cutoff (%) |
| `dice_concordance` | `0.10` | Spatial overlap cutoff |
| `allow_partial_aggregate` | `true` | Cohort CSV without all subjects |
| `pipeline_version` | `meldhip` | Written to cohort CSV |

## Lesion analysis

Ported from [MELD_CBF](../Meld_CBF/pipeline). CBF registration is **not** used; the scalar map is MELD `T1.mgz`, which already shares the `prediction.nii.gz` grid.

| MELD_CBF | Meld_Hippunfold |
|----------|-----------------|
| `cbf_register_in_container.sh` | Skipped |
| `cbf_stats.py` | `workflow/analysis/lesion_stats.py` |
| `cbf_visualize.py` | `workflow/analysis/lesion_visualize.py` |
| `aggregate_stats.py` | `workflow/scripts/aggregate_lesion_stats.py` |

### Per-subject stats CSV columns

One row per cluster plus `all_clusters` (or `none` if MELD-negative).

| Column | Meaning |
|--------|---------|
| `scalar_mean`, `scalar_std`, `scalar_median` | T1 intensity in cluster |
| `gm_z` | Cluster mean vs cortical GM (subject-normalized) |
| `host_roi`, `host_roi_name` | Dominant aparc+aseg label in cluster |
| `ipsi_roi_scalar`, `contra_roi_scalar` | Mean T1 in host ROI vs homologue (+1000) |
| `roi_asym_pct` | ROI L↔R asymmetry (%); negative ⇒ ipsilateral lower |
| `cluster_mirror_ai` | Lesion mask flipped L↔R; `(ipsi−contra)/(ipsi+contra)` |
| `frac_hypo`, `dice_hypo` | Overlap with voxelwise GM z < `hypo_z` |
| `hipp_overlap_*` | Overlap with fused HippUnfold subfields (extension) |

Column names `hypoperfused`, `frac_hypo`, `dice_hypo` match MELD_CBF for tooling compatibility; with T1 they reflect **structural** GM deviation, not perfusion.

### Concordance call (`cohort_lesion_stats.csv`)

Applied on each row (interpret at `cluster == all_clusters` for lesion-level summary):

```
hypoperfused       = roi_asym_pct <= asym_concordance_pct
spatial_concordant = dice_hypo    >= dice_concordance
concordance_call   = concordant | partial | discordant
```

### Statistics formulas

Let **ipsi** and **contra** denote ipsilateral and contralateral means on the T1 map.

**GM z-score:**

$$z = \frac{\overline{T1}_{\mathrm{cluster}} - \mu_{\mathrm{GM}}}{\sigma_{\mathrm{GM}}}$$

**ROI asymmetry** (FreeSurfer homologue pair):

$$\mathrm{roi\_asym\_pct} = \frac{T1_{\mathrm{ipsi\,ROI}} - T1_{\mathrm{contra\,ROI}}}{\tfrac{1}{2}(T1_{\mathrm{ipsi\,ROI}} + T1_{\mathrm{contra\,ROI}})} \times 100$$

**Cluster mirror asymmetry:**

$$\mathrm{cluster\_mirror\_ai} = \frac{T1_{\mathrm{ipsi}} - T1_{\mathrm{contra}}}{T1_{\mathrm{ipsi}} + T1_{\mathrm{contra}}}$$

**Concordance:**

$$\mathrm{frac\_hypo} = \frac{\#\{\mathrm{cluster\ voxels\ with\ } z < \mathrm{hypo\_z}\}}{\#\mathrm{cluster\ voxels}}$$

$$\mathrm{dice\_hypo} = \frac{2\,|\mathrm{cluster} \cap \mathrm{hypo\_GM}|}{|\mathrm{cluster}| + |\mathrm{hypo\_GM}|}$$

## Upstream container notes

- **MELD Graph** — image layout, `meld-docker` wrapper, licenses, models: [meld.md](meld.md)
- **HippUnfold** — BIDS App entrypoint, cache dir, `run_hippunfold.sh`: [hip.md](hip.md)

## SLURM

`./meldhip start` submits `slurm_meldhip.slurm` from the repo root. Defaults: 48 h, 8 CPUs, 64 GB RAM. Edit the `#SBATCH` lines for your partition/account.

The job sources `.meldhip/run_config.env`, activates `.meldhip/venv`, and runs Snakemake with `--keep-going`.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `./meldhip check` fails on licenses/models | Copy from MELD Graph setup into `meld_data/` per check output |
| HippUnfold fusion fails | Run with `--output_spaces T1w`; confirm `*desc-subfields_dseg.nii.gz` under `hippunfold/<sub>/anat/` |
| Empty ROI / asymmetry columns | `aparc+aseg.mgz` missing — MELD FreeSurfer step may have failed |
| Snakemake NFS stale files | Increase `SNAKEMAKE_LATENCY_WAIT` in `production.env` |
| Apptainer pull / tmp errors | Set `TMPDIR` and `APPTAINER_TMPDIR` to a writable path (see `./meldhip install`) |
| Re-run one subject | `./meldhip start -i <bids> -p <sub>` — Snakemake resumes from last outputs |

## Snakemake rules

| Rule | Purpose |
|------|---------|
| `meld_prepare` | Stage BIDS → MELD input; `meld-docker cohort sync` |
| `meld_predict` | `meld-docker run <sub>` |
| `hippunfold_predict` | `run_hippunfold.sh` per subject |
| `fuse_to_meld_space` | Resample subfields → MELD prediction grid |
| `lesion_stats` | Per-subject CSV (T1 + aparc + hipp overlap) |
| `lesion_visualize` | PNG overlays (optional) |
| `lesion_aggregate` | Cohort CSV + concordance |

Dry-run locally:

```bash
./meldhip start -i /path/to/bids --dry-run
```
