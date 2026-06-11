# MELD Graph container

This note describes how the **MELD Graph** container is built and run in the upstream project [**MELDProject/meld_graph**](https://github.com/MELDProject/meld_graph) (graph-based FCD lesion segmentation for the MELD pipeline). Full user guides live in the [MELD Graph documentation](https://meld-graph.readthedocs.io/) (Docker and Singularity/Apptainer install pages).

## What the container is for

The image bundles everything needed to run the **new patient prediction pipeline** on a host: FreeSurfer, optional FastSurfer, the Python `meld_graph` environment (PyTorch, PyG, etc.), and the application code under `/app`. Data, models, harmonisation parameters, and licenses are expected from the host via mounts or secrets, not baked into the image.

## Published image

The team publishes images on Docker Hub under **`meldproject/meld_graph`**, with version tags (for example `v2.2.4`, `latest`, and a GPU-oriented variant where applicable). HPC sites typically convert the Docker image to Singularity/Apptainer with:

`apptainer build meld_graph.sif docker://meldproject/meld_graph:<tag>`

## Multi-stage Dockerfile (build logic)

The [`Dockerfile`](https://github.com/MELDProject/meld_graph/blob/main/Dockerfile) uses two stages:

1. **`micromamba` stage**  
   - Base: `mambaorg/micromamba:latest`.  
   - Creates the Conda environment **`meld_graph`** from the repo’s [`environment.yml`](https://github.com/MELDProject/meld_graph/blob/main/environment.yml).  
   - This layer is expensive but stable; it is copied into the final image rather than rebuilt on every small code change.

2. **`MELDgraph` stage (runtime)**  
   - Base: `debian:12-slim`.  
   - **FreeSurfer 7.2.0** is downloaded and unpacked under `/opt/freesurfer-7.2.0`, with several large optional directories excluded to save space.  
   - **FastSurfer** is cloned (pinned branch, e.g. v1.1.2) under `/opt/fastsurfer-v1.1.2` with `FASTSURFER_HOME` set accordingly.  
   - The **`meld_graph` Conda env** is copied from the first stage into `/opt/conda/envs/meld_graph`.  
   - The repository is **`COPY . .`** into **`/app`** (working directory).  
   - Additional Python pins are installed inside that env (Torch, editable install of the package, `torch-scatter`, `torch-geometric`, `captum`, etc.).  
   - **`PATH`** is set so `/opt/conda/envs/meld_graph/bin` comes first; micromamba activation is wired into `~/.bashrc` for interactive shells.  
   - **`/data`** is created as the conventional mount point for pipeline inputs/outputs on the host.  
   - Writable **`/.cache`** and **`/matlab`** are created with permissive permissions so FreeSurfer/FastSurfer do not fail on non-root container users.  
   - Environment flags such as **`KEEP_DATA_PATH=1`** and **`SILENT=1`** are set for the pipeline runtime.

## Entrypoint

[`entrypoint.sh`](https://github.com/MELDProject/meld_graph/blob/main/entrypoint.sh) is minimal by design:

- Sources **`$FREESURFER_HOME/FreeSurferEnv.sh`** so FreeSurfer is configured inside the container.  
- Executes the command passed as container arguments: **`$@`**.

So the image does not hard-code `python …`; **Docker / Compose / Singularity** supply the actual command (for example `python scripts/new_patient_pipeline/new_pt_pipeline.py …`). That matches the documented invocations in the [FAQs](https://github.com/MELDProject/meld_graph/blob/main/meld_graph/docs/FAQs.md) and install guides.

The Dockerfile sets:

```dockerfile
ENTRYPOINT ["/bin/bash", "entrypoint.sh"]
```

so the default process is `bash entrypoint.sh <your-args>`.

## Docker Compose (workstation pattern)

[`compose.yml`](https://github.com/MELDProject/meld_graph/blob/main/compose.yml) defines a service **`meld_graph`** that:

- Uses **`meldproject/meld_graph:latest`** with **`platform: linux/amd64`**.  
- Mounts **`./docker-data` → `/data`** for persistent data.  
- Passes **FreeSurfer** and **MELD** license file paths via **Docker secrets**, mapped to **`/run/secrets/license.txt`** and **`/run/secrets/meld_license.txt`**, with environment variables **`FS_LICENSE`** and **`MELD_LICENSE`** pointing at those paths.  
- Runs as **`user: $DOCKER_USER`** so file ownership on the bind mount matches the host user (set `DOCKER_USER` to `uid:gid`, e.g. from `id -u` / `id -g`).  
- Declares **GPU** device reservations with **`count: 0`** by default so GPU is optional unless you raise the count for GPU-enabled images.

Typical usage from the repo is along the lines of:

`DOCKER_USER="$(id -u):$(id -g)" docker compose run meld_graph <command>`

where `<command>` is whatever the pipeline docs specify (often `python scripts/new_patient_pipeline/...`).

## Licenses and paths inside the container

- **FreeSurfer** expects a license; in Compose this is **`FS_LICENSE=/run/secrets/license.txt`**. The Dockerfile also documents **`FS_LICENSE=/license.txt`** in shell profile for images run with a single license file bind-mounted to `/license.txt`.  
- **MELD Graph** v2.2.4+ requires a **MELD license** file (registration described in the upstream [README](https://github.com/MELDProject/meld_graph/blob/main/README.md)); Compose uses **`MELD_LICENSE=/run/secrets/meld_license.txt`**.

Always follow the version-specific install pages on Read the Docs for exact paths and verification commands.

## Native helper script (not the container itself)

[`meldgraph.sh`](https://github.com/MELDProject/meld_graph/blob/main/meldgraph.sh) is for **native** Conda installs: it activates `meld_graph` and dispatches to `python scripts/new_patient_pipeline/...` or `pytest`. It illustrates the same entry module as the container but is **not** used as the container entrypoint.

## Singularity / Apptainer on HPC

Docker-in-Docker is often unavailable on clusters; the project documents **Singularity/Apptainer** workflows (bind-mount host **`/data`**, bind license files, `cd /app`, `source $FREESURFER_HOME/FreeSurferEnv.sh`, then run the same `python` commands). See [Install Singularity](https://meld-graph.readthedocs.io/en/latest/install_singularity.html) in the official docs.

## Reusing our `docker_version/meld-docker` wrapper

This workspace can **reuse the same Apptainer/Singularity orchestration** already maintained under **`docker_version/meld-docker`** in the lab’s MELD Graph tree (for example `../Meld_Graph/docker_version/meld-docker` relative to this folder). That script is **not** part of upstream [meld_graph](https://github.com/MELDProject/meld_graph); it is a thin, opinionated layer on top of the official **`meldproject/meld_graph`** image converted to a `.sif` file.

### What it does

- Resolves **`apptainer`** or **`singularity`** on `PATH`, then runs **`exec`** on a local image (default: `meld_graph_v2.2.4.sif` next to the script, overridable with **`MELD_CONTAINER_IMAGE`**).
- Bind-mounts the data tree to **`/data`** (default **`MELD_DATA_DIR`** = `${MELD_DEPLOY_ROOT}/meld_data`), matching the container’s expected layout.
- Bind-mounts **FreeSurfer** and **MELD** license files to **`/license.txt`** and **`/meld_license.txt`**, and sets **`FS_LICENSE`** / **`MELD_LICENSE`** inside the container to those paths—the same convention the upstream docs use for Apptainer.
- Runs the pipeline with the same inner pattern as the official singularity instructions: `cd /app`, **`source $FREESURFER_HOME/FreeSurferEnv.sh`**, then **`python scripts/new_patient_pipeline/new_pt_pipeline.py …`**. That mirrors **`entrypoint.sh`** (FreeSurfer env first, then your command).
- Sets **`PYTHONNOUSERSITE=1`** so a user’s **`~/.local`** Python packages on the host cannot shadow the Conda stack inside the image (avoids numpy ABI mismatches on shared NFS home directories).
- Optionally bind-mounts **`meld_params`** and **`models`** when they live outside **`meld_data`** via **`MELD_PARAMS_SRC`** and **`MODELS_SRC`**.

### Layout and configuration

| Variable (optional) | Role |
|---------------------|------|
| **`MELD_DEPLOY_ROOT`** | Directory containing `meld-docker`, the `.sif`, license files, and (by default) `meld_data/`. Defaults to the script’s directory. |
| **`MELD_DATA_DIR`** | Host path mounted at **`/data`** (input, output, logs, locks, etc.). |
| **`MELD_FS_LICENSE`** / **`MELD_MELD_LICENSE`** | Override paths to the two license files (defaults: `freesurfer_license.txt` and `meld_license.txt` under deploy root). |
| **`MELD_PARAMS_SRC`**, **`MODELS_SRC`** | Extra read-only binds to **`/data/meld_params`** and **`/data/models`** when those trees are not under `meld_data`. |

If **`production.env`** exists beside **`meld-docker`**, it is sourced automatically (see **`production.env.example`** in the same directory). **`meld_production.sh`** in that folder is a small dispatcher that forwards to **`meld-docker`** with shorthand subcommands (`sync`, `run-cohort`, `slurm-cohort`).

### Commands you get for free

The wrapper implements **`check`**, **`run`**, **`batch`**, **`cohort`** (sync + per-cohort runs), **`status`**, **`validate`**, **`logs`**, **`results`**, **`shell`**, and **`slurm`** / **`slurm cohort`** (subject or whole cohort on SLURM). Those commands only **prepare the host** (symlinks from cohort folders into `meld_data/input/`, BIDS root JSON stubs, locks, logging) and then invoke the **same** container entry pattern as upstream.

### How to reuse from Meld_Hippunfold

1. Keep one **Apptainer image** built from Docker Hub, e.g. `apptainer build meld_graph_v2.2.4.sif docker://meldproject/meld_graph:v2.2.4`, in a directory that also holds **`meld-docker`** and the two license files (or set the env vars above).
2. Point **`MELD_DEPLOY_ROOT`** or run the script from that directory so **`meld_data/`** (or **`MELD_DATA_DIR`**) matches your cohort layout.
3. From this repo, call the wrapper by absolute path or add a symlink, for example:  
   `bash /path/to/Meld_Graph/docker_version/meld-docker check`  
   then **`run`**, **`slurm`**, etc., as in that script’s help text.

You do **not** need to duplicate FreeSurfer/MELD/Python setup in Meld_Hippunfold if this wrapper already encodes your cluster’s conventions.

## References

- Repository: [https://github.com/MELDProject/meld_graph](https://github.com/MELDProject/meld_graph)  
- Documentation: [https://meld-graph.readthedocs.io/](https://meld-graph.readthedocs.io/)  
- Docker install: [https://meld-graph.readthedocs.io/en/latest/install_docker.html](https://meld-graph.readthedocs.io/en/latest/install_docker.html)  
- Singularity install: [https://meld-graph.readthedocs.io/en/latest/install_singularity.html](https://meld-graph.readthedocs.io/en/latest/install_singularity.html)
