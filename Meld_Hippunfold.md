# Meld_Hippunfold — full pipeline reference

End-to-end documentation for the **Meld_Hippunfold** Snakemake pipeline: MELD Graph FCD lesion prediction, HippUnfold hippocampal subfield segmentation, native-T1 fusion, and MELD_CBF-style lesion asymmetry / concordance analysis on structural T1.

For a short quick start see [README.md](README.md). For CLI, config, and troubleshooting see [USER_GUIDE.md](USER_GUIDE.md).

---

## 1. What the pipeline does

Given a **BIDS** dataset with T1w per subject, Meld_Hippunfold:

1. Runs **MELD Graph** (FreeSurfer recon + graph neural network) → cortical FCD lesion map.
2. Runs **HippUnfold** (nnU-Net subfield segmentation) → hippocampal subfield labels in native T1w space.
3. **Fuses** HippUnfold subfields onto the MELD `prediction.nii.gz` voxel grid.
4. Computes **lesion statistics** (ROI asymmetry, mirror asymmetry, GM z-scores, hipp overlap) and a cohort **concordance call**.

MELD and HippUnfold are **independent** container runs on the same BIDS input. Fusion is a lightweight resampling step — there is no joint registration product from upstream tools.

```mermaid
flowchart TB
    subgraph input [Input]
        BIDS["BIDS dataset<br/>sub-*/ses-*/anat/*_T1w.nii.gz"]
    end

    subgraph parallel [Parallel per subject]
        MELD["MELD Graph<br/>(Apptainer)"]
        HIPP["HippUnfold<br/>(Apptainer)"]
    end

    subgraph meld_out [MELD outputs]
        PRED["prediction.nii.gz"]
        T1["T1.mgz"]
        APARC["aparc+aseg.mgz"]
    end

    subgraph hipp_out [HippUnfold outputs]
        SUBF["*desc-subfields_dseg.nii.gz<br/>(T1w space)"]
    end

    subgraph post [Post-processing — host Python]
        FUSE["fuse_hippunfold_to_meld.py"]
        STATS["lesion_stats.py"]
        VIZ["lesion_visualize.py"]
        AGG["aggregate_lesion_stats.py"]
    end

    BIDS --> MELD
    BIDS --> HIPP
    MELD --> PRED & T1 & APARC
    HIPP --> SUBF
    PRED --> FUSE
    SUBF --> FUSE
    FUSE --> STATS
    PRED & T1 & APARC --> STATS
    T1 & PRED & FUSE --> VIZ
    STATS --> AGG
```

---

## 2. System architecture

The pipeline **orchestrates** existing lab container deployments; it does not rebuild MELD or HippUnfold images.

```mermaid
flowchart LR
    subgraph host [Login / compute node]
        CLI["./meldhip"]
        SM["Snakemake<br/>(.meldhip/venv)"]
        SLURM["slurm_meldhip.slurm"]
    end

    subgraph siblings [Sibling repos — not in this git tree]
        MD["meld-docker<br/>+ meld_graph_*.sif<br/>+ licenses + models"]
        HH["run_hippunfold.sh<br/>+ khanlab_hippunfold_*.sif"]
    end

    subgraph work [Work directory — per run]
        WD["work/ or work/custom/<br/>meld_data | hippunfold | fused"]
    end

    CLI -->|start| SLURM
    SLURM --> SM
    SM -->|meld_predict| MD
    SM -->|hippunfold_predict| HH
    SM -->|fusion + analysis| host
    MD --> WD
    HH --> WD
```

| Layer | Component | Role |
|-------|-----------|------|
| CLI | `./meldhip` | `install`, `check`, `start`, `logs` |
| Scheduler | SLURM + `slurm_meldhip.slurm` | Single job runs full Snakemake DAG |
| Orchestration | Snakemake `workflow/Snakefile` | DAG, resume, resource limits |
| MELD | `meld-docker` in Apptainer SIF | FreeSurfer + MELD Graph GNN |
| HippUnfold | `run_hippunfold.sh` + SIF | BIDS App, nnU-Net subfields |
| Host Python | venv | Fusion, stats, viz, aggregate |

Site paths are set in `production.env` (gitignored). Runtime paths are written to `.meldhip/run_config.env` on each `./meldhip start`.

---

## 3. Snakemake DAG (all rules)

Per-subject rules run in parallel where dependencies allow. `meld_prepare` runs once per cohort; `lesion_aggregate` runs once at the end.

```mermaid
flowchart TD
    ALL["rule all"]

    PREP["meld_prepare<br/>BIDS → meld_data/from_bids<br/>meld-docker cohort sync"]
    MELD["meld_predict<br/>meld-docker run &lt;sub&gt;"]
    HIPP["hippunfold_predict<br/>run_hippunfold.sh"]
    FUSE["fuse_to_meld_space<br/>fuse_hippunfold_to_meld.py"]
    STATS["lesion_stats<br/>lesion_stats.py"]
    VIZ["lesion_visualize<br/>lesion_visualize.py"]
    AGG["lesion_aggregate<br/>aggregate_lesion_stats.py"]

    ALL --> PREP
    ALL --> MELD
    ALL --> HIPP
    ALL --> FUSE
    ALL --> STATS
    ALL --> VIZ
    ALL --> AGG

    PREP --> MELD
    HIPP --> FUSE
    MELD --> FUSE
    FUSE --> STATS
    MELD --> STATS
    STATS --> VIZ
    STATS --> AGG
```

ASCII equivalent (dependency-only):

```
                    ┌─────────────────┐
                    │   meld_prepare  │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   │                   ▼
┌─────────────────┐         │        ┌──────────────────────┐
│  meld_predict   │         │        │ hippunfold_predict   │
│  (per subject)  │         │        │   (per subject)      │
└────────┬────────┘         │        └──────────┬───────────┘
         │                   │                   │
         └─────────┬─────────┘                   │
                   ▼                             │
         ┌─────────────────┐                   │
         │ fuse_to_meld_   │◄──────────────────┘
         │     space       │
         └────────┬────────┘
                  │
         ┌────────┴────────┐
         ▼                 ▼
┌─────────────────┐  ┌─────────────────┐
│  lesion_stats   │  │lesion_visualize │  (optional)
└────────┬────────┘  └─────────────────┘
         │
         ▼
┌─────────────────┐
│lesion_aggregate │  (once per cohort)
└─────────────────┘
```

### Rule summary

| Rule | Container / runtime | Primary outputs |
|------|---------------------|-----------------|
| `meld_prepare` | bash + `meld-docker cohort sync` | `meld_data/.cohort_synced` |
| `meld_predict` | MELD Apptainer | `prediction.nii.gz`, `T1.mgz`, `aparc+aseg.mgz` |
| `hippunfold_predict` | HippUnfold Apptainer | `hippunfold/<sub>/anat/*subfields_dseg*` |
| `fuse_to_meld_space` | host Python (nibabel) | `fused/<sub>/hipp_subfields_in_meld_space.nii.gz` |
| `lesion_stats` | host Python | `analysis/<sub>/lesion_in_clusters_<sub>.csv` |
| `lesion_visualize` | host Python (nilearn) | `analysis/<sub>/figures/*.png` |
| `lesion_aggregate` | host Python (pandas) | `output/cohort_lesion_stats.csv` |

**Resource limits** (Snakemake `--resources`): `heavy_fs=1` caps concurrent MELD jobs; `hippunfold=2` caps concurrent HippUnfold jobs.

---

## 4. Per-subject data flow

### 4.1 MELD branch

```mermaid
sequenceDiagram
    participant BIDS
    participant Prep as prepare_meld_from_bids
    participant Sync as meld-docker cohort sync
    participant Run as meld-docker run
    participant FS as FreeSurfer (in SIF)
    participant GNN as MELD Graph (in SIF)

    BIDS->>Prep: link sub-* → meld_data/from_bids/
    Prep->>Sync: stage input/ tree
    Sync->>Run: ready
    Run->>FS: recon + surfaces + aparc+aseg
    Run->>GNN: surface features → lesion clusters
    Run-->>Run: prediction.nii.gz on T1 grid
```

MELD writes `prediction.nii.gz` in **FreeSurfer conformed T1 space** — same geometry as `output/fs_outputs/<sub>/mri/T1.mgz`. All downstream MELD-grid analysis uses this grid.

### 4.2 HippUnfold branch

```mermaid
sequenceDiagram
    participant BIDS
    participant HIPP as run_hippunfold.sh
    participant NN as nnU-Net (in SIF)

    BIDS->>HIPP: participant --modality T1w --output_spaces T1w
    HIPP->>NN: subfield segmentation L/R
    HIPP-->>HIPP: hippunfold/<sub>/anat/*desc-subfields_dseg.nii.gz
```

HippUnfold must run with `--output_spaces T1w` so subfield segmentations are in native T1w space (required for fusion).

### 4.3 Fusion — why and how

MELD and HippUnfold never register to each other. Fusion resamples HippUnfold labels **onto the MELD prediction grid**:

```
  HippUnfold T1w grid                    MELD prediction grid
  ┌──────────────────┐                   ┌──────────────────┐
  │ CA1  DG  subiculum│  resample_from_to │ prediction labels │
  │  (native T1w)     │  ───────────────► │  + hipp subfields │
  └──────────────────┘      order=0       └──────────────────┘
         ▲                                        ▲
         │                                        │
    HippUnfold                              MELD Graph
    subfields_dseg                          prediction.nii.gz
```

Script: `workflow/scripts/fuse_hippunfold_to_meld.py`

- Finds `*space-T1w*desc-subfields_dseg.nii.gz` (both hemispheres).
- Combines hemi labels with per-voxel `maximum`.
- Resamples to MELD `prediction.nii.gz` with nearest neighbour (`order=0`).
- Writes `fusion_manifest.json` with provenance.

---

## 5. Lesion analysis branch

Ported from [MELD_CBF](../Meld_CBF/pipeline). **No CBF perfusion map** — the scalar map is MELD `T1.mgz` (already on the prediction grid; no extra registration).

```mermaid
flowchart LR
    subgraph inputs [Inputs on MELD grid]
        T1["T1.mgz<br/>(scalar map)"]
        PRED["prediction.nii.gz<br/>(lesion mask)"]
        APARC["aparc+aseg.mgz<br/>(ROI labels)"]
        HIPP["hipp_subfields<br/>in_meld_space"]
    end

    subgraph metrics [Per-cluster metrics]
        GMZ["gm_z"]
        ROI["roi_asym_pct"]
        MIR["cluster_mirror_ai"]
        HYP["frac_hypo / dice_hypo"]
        HO["hipp_overlap_*"]
    end

    subgraph cohort [Cohort]
        CALL["concordance_call<br/>concordant | partial | discordant"]
    end

    T1 & PRED & APARC --> GMZ & ROI & MIR & HYP
    HIPP --> HO
    GMZ & ROI & MIR & HYP & HO --> CALL
```

### Concordance logic (same thresholds as MELD_CBF)

```
hypoperfused       = roi_asym_pct <= asym_concordance_pct   (default −8%)
spatial_concordant = dice_hypo    >= dice_concordance        (default 0.10)

concordance_call   = concordant   if both true
                   = partial     if either true
                   = discordant  otherwise
```

With T1 as the scalar map, `hypoperfused` / `frac_hypo` / `dice_hypo` index **structural** GM deviation, not perfusion. Column names match MELD_CBF for tooling compatibility.

---

## 6. Directory layout

Example after `./meldhip start -i <bids> -w work/mycohort -p sub-001 sub-002`:

```
Meld_Hippunfold/
├── meldhip                          CLI entrypoint
├── production.env                   site paths (local, gitignored)
├── .meldhip/
│   ├── run_config.env               last start parameters
│   ├── last_job_id                  SLURM job id
│   └── venv/                        Snakemake + analysis Python
├── config/config.yaml
├── slurm_meldhip.slurm
└── work/mycohort/
    ├── meld_data/
    │   ├── from_bids/sub-001/ …     symlinks to BIDS
    │   ├── input/sub-001/ …         meld-docker staging
    │   ├── models/  meld_params/    seeded from deploy bundle
    │   └── output/
    │       ├── fs_outputs/sub-001/mri/
    │       │   ├── T1.mgz
    │       │   └── aparc+aseg.mgz
    │       ├── predictions_reports/sub-001/predictions/
    │       │   └── prediction.nii.gz
    │       ├── analysis/sub-001/
    │       │   ├── lesion_in_clusters_sub-001.csv
    │       │   └── figures/*.png
    │       └── cohort_lesion_stats.csv
    ├── hippunfold/sub-001/anat/
    │   └── *desc-subfields_dseg.nii.gz
    └── fused/sub-001/
        ├── hipp_subfields_in_meld_space.nii.gz
        └── fusion_manifest.json
```

---

## 7. Inputs and outputs

### Inputs

| Requirement | Location / notes |
|-------------|------------------|
| BIDS T1w | `sub-*/ses-*/anat/*_T1w.nii.gz` |
| MELD SIF + licenses | `MELD_DEPLOY_ROOT` (see `production.env`) |
| MELD models + params | `meld_data/models`, `meld_data/meld_params` (auto-seeded) |
| HippUnfold SIF | `HIPPUNFOLD_SIF` or `../HippUnfold/*.sif` |
| Subject filter | `-p sub-001 sub-002` or all `sub-*` in BIDS |

### Final targets (`rule all`)

| Output | Description |
|--------|-------------|
| `fused/<sub>/hipp_subfields_in_meld_space.nii.gz` | Subfields on MELD grid |
| `analysis/<sub>/lesion_in_clusters_<sub>.csv` | Per-lesion statistics |
| `output/cohort_lesion_stats.csv` | Cohort table + concordance |
| `analysis/<sub>/figures/*.png` | Overlays (if `enable_analysis_viz: true`) |

---

## 8. Running the pipeline

```bash
# One-time setup
cp production.env.example production.env   # edit paths
./meldhip install
./meldhip check

# Full cohort
./meldhip start -i /path/to/bids

# Named subjects + separate work tree
./meldhip start -i /path/to/bids \
  -w work/mycohort \
  -p sub-001 sub-002

# Plan without submitting
./meldhip start -i /path/to/bids --dry-run

# Monitor
squeue -j <jobid>
./meldhip logs -f
```

### SLURM job sketch

```
  login node                         compute node
 ┌─────────────┐                    ┌─────────────────────────────┐
 │ ./meldhip   │  sbatch          │ slurm_meldhip.slurm         │
 │   start     │ ───────────────► │  → activate venv            │
 └─────────────┘                  │  → snakemake -s Snakefile   │
                                  │     (48h, 8 CPU, 64G)       │
                                  └─────────────────────────────┘
```

Default `#SBATCH`: 48 h, 8 CPUs, 64 G RAM — edit `slurm_meldhip.slurm` for your partition/account.

**Runtime expectation:** `meld_predict` dominates (FreeSurfer + GNN, often **hours per subject**). HippUnfold, fusion, and analysis are shorter.

---

## 9. Configuration sketch

```
config/config.yaml          ← defaults (thresholds, resource limits)
        +
production.env              ← site paths (MELD_DEPLOY_ROOT, SIF overrides)
        +
./meldhip start -i … -p …   ← BIDS, work_dir, subject filter
        +
.meldhip/run_config.env     ← written at start, read by SLURM job
        +
slurm_meldhip.slurm --config  ← passes bids_dir, subjects[], flags into Snakemake
```

Key analysis keys in `config/config.yaml`:

| Key | Default | Purpose |
|-----|---------|---------|
| `hypo_z` | `-1.5` | GM z threshold for `frac_hypo` / `dice_hypo` |
| `asym_concordance_pct` | `-8.0` | ROI asymmetry cutoff (%) |
| `dice_concordance` | `0.10` | Spatial overlap cutoff |
| `enable_analysis_viz` | `true` | PNG overlays |

---

## 10. Repository map

```
workflow/
├── Snakefile                         full DAG
├── scripts/
│   ├── prepare_meld_from_bids.sh     BIDS → meld_data cohort links
│   ├── fuse_hippunfold_to_meld.py    HippUnfold → MELD grid
│   └── aggregate_lesion_stats.py     cohort CSV + concordance
└── analysis/
    ├── lesion_stats.py               per-subject CSV (MELD_CBF port)
    └── lesion_visualize.py           T1 / lesion / subfield PNGs
```

---

## 11. Related documentation

| Document | Contents |
|----------|----------|
| [README.md](README.md) | Quick start, outputs, citations |
| [USER_GUIDE.md](USER_GUIDE.md) | CLI, config tables, formulas, troubleshooting |
| [meld.md](meld.md) | MELD Graph container + `meld-docker` |
| [hip.md](hip.md) | HippUnfold container + `run_hippunfold.sh` |

---

## 12. Citations

See [README.md — Citations](README.md#citations) for MELD Graph, HippUnfold, FreeSurfer, BIDS, Snakemake, and related papers.
