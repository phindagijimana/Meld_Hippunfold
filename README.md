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

- **[Meld_Hippunfold.md](Meld_Hippunfold.md)** — full pipeline reference with diagrams
- **[USER_GUIDE.md](USER_GUIDE.md)** — CLI, config, metrics, troubleshooting
- **[meld.md](meld.md)** — MELD Graph container and `meld-docker` reuse
- **[hip.md](hip.md)** — HippUnfold container and `run_hippunfold.sh` reuse

## Citations

If you use this pipeline in research, cite the primary methods papers below and this repository as appropriate.

### Core methods

| Tool | Citation |
|------|----------|
| **MELD Graph** | Ripart M, Spitzer H, Williams LZJ, et al. Detection of Epileptogenic Focal Cortical Dysplasia Using Graph Neural Networks: A MELD Study. *JAMA Neurol*. 2025;82(4):397-406. https://doi.org/10.1001/jamaneurol.2024.5406 |
| **HippUnfold** | DeKraker J, Haast RA, Yousif MD, et al. Automated hippocampal unfolding for morphometry and subfield segmentation with HippUnfold. *eLife*. 2022;11:e77945. https://doi.org/10.7554/eLife.77945 |
| **HippUnfold ≥ 1.3** (unfolded-space atlas) | DeKraker J, Palomero-Gallagher N, Kedo O, et al. Evaluation of surface-based hippocampal registration using ground-truth subfield definitions. *eLife*. 2023;12:RP88404. https://doi.org/10.7554/eLife.88404.3 |

### Supporting software and standards

| Resource | Citation / link |
|----------|-----------------|
| **MELD (original FCD pipeline)** | Spitzer H, Ripart M, et al. Interpretable surface-based detection of focal cortical dysplasias: a multi-centre epilepsy lesion detection study. *Brain*. 2022. https://doi.org/10.1093/brain/awac224 |
| **FreeSurfer** (MELD recon, `aparc+aseg` ROIs) | Fischl B. FreeSurfer. *NeuroImage*. 2012;62(2):774-781. https://doi.org/10.1016/j.neuroimage.2012.01.021 |
| **nnU-Net** (HippUnfold segmentation backend) | Isensee F, Jaeger PF, Kohl SAA, et al. nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. *Nat Methods*. 2021;18(2):203-211. https://doi.org/10.1038/s41592-020-01008-z |
| **BIDS** | Gorgolewski KJ, Auer T, Calhoun VD, et al. The brain imaging data structure. *Sci Data*. 2016;3:160044. https://doi.org/10.1038/sdata.2016.44 |
| **BIDS Apps** | Gorgolewski KJ, Burns CD, Madison C, et al. BIDS Apps. *PLOS Comput Biol*. 2017;13(3):e1005209. https://doi.org/10.1371/journal.pcbi.1005209 |
| **Snakemake** | Mölder F, Jablonski KP, Letcher B, et al. Sustainable data analysis with Snakemake. *F1000Res*. 2021;10:33. https://doi.org/10.12688/f1000research.29032.2 |

### Software and documentation

- MELD Graph: https://github.com/MELDProject/meld_graph — https://meld-graph.readthedocs.io/
- HippUnfold: https://github.com/khanlab/hippunfold — https://hippunfold.readthedocs.io/
- Lesion asymmetry / concordance analysis follows the same framework as the lab [MELD_CBF](../Meld_CBF/pipeline) pipeline (structural T1 scalar map; no CBF perfusion input).

## Production checklist

| Step | Command |
|------|---------|
| Site paths | Edit `production.env` (optional) |
| Images + venv | `./meldhip install` |
| Preflight | `./meldhip check` |
| Run cohort | `./meldhip start -i <bids>` |
| Monitor | `./meldhip logs -f` / `squeue -u $USER` |
