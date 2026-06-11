#!/usr/bin/env python3
"""
Lesion ↔ structural statistics in MELD conformed grid (Meld_Hippunfold).

Port of MELD_CBF cbf_stats.py: same per-cluster metrics and concordance inputs,
using a structural scalar map (default: MELD T1.mgz) instead of registered CBF.
Optional fused HippUnfold subfields add hippocampal overlap columns.

Usage:
  lesion_stats.py <subject> <scalar.nii.gz> <prediction.nii.gz> <aparc+aseg.mgz> \\
      <out_csv> [hipp_subfields.nii.gz] [hypo_z]
"""
from __future__ import annotations

import csv
import os
import sys

import nibabel as nib
import numpy as np

HYPO_Z_DEFAULT = -1.5


def load_like(path, ref_img):
    """Load an image; nearest-resample onto ref grid if geometry differs."""
    img = nib.load(path)
    if img.shape[:3] == ref_img.shape[:3] and np.allclose(img.affine, ref_img.affine, atol=1e-3):
        return np.asarray(img.get_fdata())
    try:
        from nilearn.image import resample_to_img

        resampled = resample_to_img(img, ref_img, interpolation="nearest")
    except Exception as exc:
        raise RuntimeError(
            f"could not resample {os.path.basename(path)} onto reference grid: {exc}"
        ) from exc
    out = resampled if hasattr(resampled, "get_fdata") else resampled
    data = np.asarray(out.get_fdata() if hasattr(out, "get_fdata") else out)
    if data.shape[:3] != ref_img.shape[:3]:
        raise RuntimeError(
            f"{os.path.basename(path)} shape {data.shape[:3]} != ref {ref_img.shape[:3]}"
        )
    return data


def is_cortical(lbl):
    lbl = int(lbl)
    return (1000 <= lbl <= 1035) or (2000 <= lbl <= 2035) or \
           (11100 <= lbl <= 11175) or (12100 <= lbl <= 12175)


def homologue(lbl):
    """Contralateral label for a cortical aparc+aseg label (L↔R offset 1000)."""
    lbl = int(lbl)
    if (1000 <= lbl <= 1035) or (11100 <= lbl <= 11175):
        return lbl + 1000
    if (2000 <= lbl <= 2035) or (12100 <= lbl <= 12175):
        return lbl - 1000
    return None


def load_lut():
    fs = os.environ.get("FREESURFER_HOME", "")
    path = os.path.join(fs, "FreeSurferColorLUT.txt")
    lut = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    lut[int(parts[0])] = parts[1]
    except Exception:
        pass
    return lut


def pct_asym(a, b):
    """Asymmetry index in %: (a−b)/mean(a,b)*100. Negative = a < b."""
    if a is None or b is None:
        return ""
    denom = (a + b) / 2.0
    if denom == 0:
        return ""
    return round((a - b) / denom * 100.0, 2)


def lr_axis(affine):
    """Voxel axis index corresponding to the world left-right (RAS x) direction."""
    cosines = np.abs(affine[:3, :3] @ np.array([1.0, 0.0, 0.0]))
    return int(np.argmax(cosines))


def mirror_asym_index(a, b):
    """Normalized asymmetry index: (a−b)/(a+b). Range ~[−1, 1]; negative = a < b."""
    if a is None or b is None:
        return ""
    denom = a + b
    if denom == 0:
        return ""
    return round((a - b) / denom, 4)


def hipp_overlap(mask, hipp, vox_mm3):
    """Lesion overlap with hippocampal subfield labels (>0)."""
    if hipp is None:
        return "", "", ""
    overlap = mask & (hipp > 0)
    n = int(overlap.sum())
    if not mask.any():
        return n, round(n * vox_mm3, 1), ""
    frac = round(n / int(mask.sum()), 3)
    return n, round(n * vox_mm3, 1), frac


def main():
    if len(sys.argv) < 6:
        print(__doc__)
        return 1

    subject, scalar_path, pred_path, aparc_path, out_csv = sys.argv[1:6]
    hipp_path = ""
    hypo_z = HYPO_Z_DEFAULT
    if len(sys.argv) > 6:
        tail = sys.argv[6:]
        for arg in tail:
            try:
                hypo_z = float(arg)
            except ValueError:
                hipp_path = arg

    scalar_img = nib.load(scalar_path)
    scalar = np.asarray(scalar_img.get_fdata())
    pred = load_like(pred_path, scalar_img)
    if not np.any(pred > 0):
        print(f"[stats] no lesion voxels in {os.path.basename(pred_path)}")
    vox = float(abs(np.linalg.det(scalar_img.affine[:3, :3])))

    hipp = None
    if hipp_path and os.path.isfile(hipp_path):
        hipp = load_like(hipp_path, scalar_img).astype(int)

    have_aparc = os.path.isfile(aparc_path)
    if have_aparc:
        aparc = load_like(aparc_path, scalar_img).astype(int)
        cortical = np.vectorize(is_cortical)(aparc) if aparc.size else np.zeros_like(aparc, bool)
        gm_mask = cortical & np.isfinite(scalar)
        gm_vals = scalar[gm_mask]
        gm_mean = float(np.mean(gm_vals)) if gm_vals.size else float("nan")
        gm_sd = float(np.std(gm_vals)) if gm_vals.size else float("nan")
        hypo_gm = np.zeros_like(scalar, bool)
        if gm_sd and np.isfinite(gm_sd) and gm_sd > 0:
            z = (scalar - gm_mean) / gm_sd
            hypo_gm = gm_mask & (z < hypo_z)
        lut = load_lut()
    else:
        print(f"[stats][WARN] aparc+aseg not found ({aparc_path}); ROI/GM metrics skipped")
        gm_mean = gm_sd = float("nan")
        hypo_gm = np.zeros_like(scalar, bool)
        aparc = None
        lut = {}

    labels = np.unique(pred[pred > 0]).astype(int)
    lr_ax = lr_axis(scalar_img.affine)
    rows = []

    def roi_mean(lbl):
        if aparc is None or lbl is None:
            return None
        m = (aparc == int(lbl)) & np.isfinite(scalar)
        return float(np.mean(scalar[m])) if m.any() else None

    def summarize(name, mask):
        vals = scalar[mask & np.isfinite(scalar)]
        n = int(vals.size)
        row = {"subject": subject, "cluster": name, "n_voxels": n,
               "volume_mm3": round(n * vox, 1)}
        if n:
            smean = float(np.mean(vals))
            row.update({
                "scalar_mean": round(smean, 4),
                "scalar_std": round(float(np.std(vals)), 4),
                "scalar_median": round(float(np.median(vals)), 4),
                "gm_z": round((smean - gm_mean) / gm_sd, 3)
                if (gm_sd and np.isfinite(gm_sd) and gm_sd > 0) else "",
            })
            host = host_name = ipsi = contra = ""
            roi_asym = clus_vs_contra = ""
            if aparc is not None:
                labs = aparc[mask]
                labs = labs[np.vectorize(is_cortical)(labs)] if labs.size else labs
                if labs.size:
                    host = int(np.bincount(labs).argmax())
                    host_name = lut.get(host, str(host))
                    h = homologue(host)
                    ipsi = roi_mean(host)
                    contra = roi_mean(h)
                    roi_asym = pct_asym(ipsi, contra)
                    clus_vs_contra = pct_asym(smean, contra)
            mirror_mask = np.flip(mask, axis=lr_ax)
            mirror_vals = scalar[mirror_mask & np.isfinite(scalar)]
            mirror_contra = float(np.mean(mirror_vals)) if mirror_vals.size else None
            mirror_ai = mirror_asym_index(smean, mirror_contra)
            frac_hypo = round(float(np.mean(hypo_gm[mask])), 3) if mask.any() else ""
            inter = int(np.sum(mask & hypo_gm))
            dice = round(2 * inter / (int(mask.sum()) + int(hypo_gm.sum())), 3) \
                if (mask.sum() + hypo_gm.sum()) else ""
            h_n, h_mm3, h_frac = hipp_overlap(mask, hipp, vox)
            row.update({
                "host_roi": host, "host_roi_name": host_name,
                "ipsi_roi_scalar": round(ipsi, 4) if isinstance(ipsi, float) else "",
                "contra_roi_scalar": round(contra, 4) if isinstance(contra, float) else "",
                "roi_asym_pct": roi_asym,
                "cluster_vs_contra_pct": clus_vs_contra,
                "cluster_mirror_ipsi_scalar": round(smean, 4),
                "cluster_mirror_contra_scalar": round(mirror_contra, 4)
                if isinstance(mirror_contra, float) else "",
                "cluster_mirror_ai": mirror_ai,
                "frac_hypo": frac_hypo, "dice_hypo": dice,
                "hipp_overlap_voxels": h_n,
                "hipp_overlap_mm3": h_mm3,
                "hipp_overlap_frac": h_frac,
            })
        return row

    if labels.size:
        rows.append(summarize("all_clusters", pred > 0))
        for lab in labels:
            rows.append(summarize(f"cluster_{lab}", pred == lab))
    else:
        rows.append({"subject": subject, "cluster": "none", "n_voxels": 0, "volume_mm3": 0})

    fields = [
        "subject", "cluster", "n_voxels", "volume_mm3",
        "scalar_mean", "scalar_std", "scalar_median", "gm_z",
        "host_roi", "host_roi_name", "ipsi_roi_scalar", "contra_roi_scalar",
        "roi_asym_pct", "cluster_vs_contra_pct",
        "cluster_mirror_ipsi_scalar", "cluster_mirror_contra_scalar", "cluster_mirror_ai",
        "frac_hypo", "dice_hypo",
        "hipp_overlap_voxels", "hipp_overlap_mm3", "hipp_overlap_frac",
    ]
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"[stats] GM mean={gm_mean:.2f} sd={gm_sd:.2f}  | {len(labels)} cluster(s); wrote {out_csv}")
    for r in rows:
        print("[stats]  ", {k: r.get(k, "") for k in
                            ("cluster", "n_voxels", "scalar_mean", "gm_z", "roi_asym_pct",
                             "cluster_mirror_ai", "frac_hypo", "dice_hypo", "hipp_overlap_frac")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
