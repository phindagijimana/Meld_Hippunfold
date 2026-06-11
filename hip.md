# HippUnfold container

This note describes how the **HippUnfold** container is built and run upstream, and how this environment can **reuse** the lab’s HPC helpers next to this folder. HippUnfold is a **BIDS App** for hippocampal unfolding and automated subfield segmentation (Snakemake-backed workflow, nnU-Net–style models in current releases).

## Official documentation

- **Khan lab manual (site you linked):** [https://hippunfold.khanlab.ca/en/latest/](https://hippunfold.khanlab.ca/en/latest/)  
- **Read the Docs (same manual, common mirror):** [https://hippunfold.readthedocs.io/en/latest/](https://hippunfold.readthedocs.io/en/latest/)  
- **Installation overview:** [https://hippunfold.readthedocs.io/en/latest/getting_started/installation.html](https://hippunfold.readthedocs.io/en/latest/getting_started/installation.html)  
- **Singularity / Apptainer (canonical run examples):** [https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md](https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md)  
- **Source:** [https://github.com/khanlab/hippunfold](https://github.com/khanlab/hippunfold)

## Published image

Images are published on Docker Hub as **`khanlab/hippunfold`**, with tags such as **`latest`** or version pins (for example **`1.5.2`**). On HPC systems without Docker, the usual pattern is to materialize a Singularity/Apptainer file:

`singularity pull khanlab_hippunfold_latest.sif docker://khanlab/hippunfold:latest`

(or the equivalent `apptainer pull`), as documented in the [Singularity getting started](https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md) guide.

## How the upstream `Dockerfile` implements the container

The main [`Dockerfile`](https://github.com/khanlab/hippunfold/blob/master/Dockerfile) in **khanlab/hippunfold** is short because heavy dependencies live in a **separate base image**:

1. **`FROM khanlab/hippunfold_deps:<version>`**  
   The **`hippunfold_deps`** image stacks the operating-system and neuroimaging toolchain the pipeline expects (see the [`hippunfold_deps`](https://github.com/khanlab/hippunfold_deps) project for details). The application Dockerfile does not reinstall that layer.

2. **`COPY . /src/`**  
   The HippUnfold repository (Snakefile, workflow, Python package) is copied into **`/src`** inside the image.

3. **No pre-baked model weights in the image (by design)**  
   Comments in the Dockerfile note that **models are not pre-downloaded** so the runtime image stays lighter; downloaded weights and templates land under a **cache directory** on first use (see below).

4. **`ENV PYTHONNOUSERSITE=1`**  
   Prevents the container’s Python from picking up arbitrary user **`site-packages`**, which keeps behavior reproducible.

5. **`RUN pip install --no-cache-dir /src`**  
   Installs the HippUnfold Python package from the copied source so the **`hippunfold`** console entry point is available.

6. **Reporting dependencies**  
   The image installs **Graphviz** and a static **ImageMagick** `magick` binary for report generation, as declared in the Dockerfile.

7. **`ENTRYPOINT [ "hippunfold" ]`**  
   The container’s default executable is the **`hippunfold`** CLI. Any arguments you pass after `docker run …` or `singularity run … image.sif` are therefore **arguments to `hippunfold`**, not to a shell. That matches the **BIDS App** calling convention used in the docs:  
   **`<bids_dir> <output_dir> <analysis_level>`** (typically **`participant`** or **`group`**), followed by HippUnfold/Snakemake options (`--modality`, `--cores`, `-p`, etc.).

So the “container implementation” is: **deps base + pip-installed HippUnfold + fixed entrypoint `hippunfold`**, with **runtime downloads** into **`HIPPUNFOLD_CACHE_DIR`** when needed (especially from v1.3 onward for nnU-Net assets).

## Runtime: Docker vs Singularity / Apptainer

- **Docker:** `docker run khanlab/hippunfold:<tag> <bids_dir> <out_dir> participant …` (with appropriate volume mounts).  
- **Singularity/Apptainer:** upstream recommends **`singularity run -e`** (or `apptainer run -e`): **`-e` / `--cleanenv`** strips most host environment variables so the container behaves predictably on shared clusters. Extra variables (for example **`HIPPUNFOLD_CACHE_DIR`**) must be passed explicitly if you need them inside the run (see the lab **`run_hippunfold.sh`** below).

**Bind paths:** If BIDS input or output live outside the default bind set, set **`SINGULARITY_BINDPATH`** / **`APPTAINER_BINDPATH`** so the container can read and write those locations (described in the same [singularity.md](https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md)).

**Disk and caches:** Pulling or building the `.sif` needs substantial space under **`/tmp`** or redirected temp dirs; the docs suggest on the order of tens of GB for build temp and roughly **~15 GB** for the image file, plus per-subject output space. Cache directory location is configurable via **`SINGULARITY_CACHEDIR`** / **`APPTAINER_CACHEDIR`** when pulls fail due to full disks.

## Reusing our `HippUnfold/` deployment helpers

The sibling checkout **`../HippUnfold/`** does **not** rebuild HippUnfold; it pulls **`docker://khanlab/hippunfold:<tag>`** and runs the same BIDS App entrypoint with HPC-oriented defaults.

| Script | Role |
|--------|------|
| **`pull_sif.sh`** | Sets **`TMPDIR`** / **`APPTAINER_TMPDIR`** / cache dirs so pulls work when **`/tmp`** is **`noexec`** or small; runs **`apptainer pull`** or **`singularity pull`** to `khanlab_hippunfold_<tag>.sif`. |
| **`run_hippunfold.sh`** | **`apptainer run -e`** (or singularity) on **`$HIPPUNFOLD_SIF`**, forwards **`HIPPUNFOLD_CACHE_DIR`** with **`--env`** when set, and sets **`PYTHONNOUSERSITE=1`** and empty **`PYTHONPATH`** so host modules do not break nnU-Net inside the image. |
| **`slurm_hippunfold.example.slurm`** | Example **`sbatch`** job: **`cd` submit dir**, temp/cache exports, **`HIPPUNFOLD_CACHE_DIR`** on scratch, **`SINGULARITY_BINDPATH`** / **`APPTAINER_BINDPATH`** for BIDS, output, and cache, then **`run_hippunfold.sh`**. |
| **`hip`** | Small convenience CLI (`install`, `start`, `logs`, …) around the same workflow. |

From **Meld_Hippunfold**, you can point at that tree with an absolute path or symlink, for example:

`bash /path/to/HippUnfold/pull_sif.sh latest`  
`export HIPPUNFOLD_SIF=/path/to/HippUnfold/khanlab_hippunfold_latest.sif`  
`bash /path/to/HippUnfold/run_hippunfold.sh /path/to/bids /path/to/out participant --modality T1w -p --cores 8`

See **`../HippUnfold/README.md`** for a full quick start and the **`hipp.md`** file there for concepts and citations.

## References

- Manual: [https://hippunfold.khanlab.ca/en/latest/](https://hippunfold.khanlab.ca/en/latest/)  
- Singularity guide (source): [https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md](https://github.com/khanlab/hippunfold/blob/master/docs/getting_started/singularity.md)  
- Application `Dockerfile`: [https://github.com/khanlab/hippunfold/blob/master/Dockerfile](https://github.com/khanlab/hippunfold/blob/master/Dockerfile)  
- Dependency base image repository: [https://github.com/khanlab/hippunfold_deps](https://github.com/khanlab/hippunfold_deps)
