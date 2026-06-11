#!/usr/bin/env python3
"""
Headless overlay PNGs after MELD + HippUnfold fusion (port of MELD_CBF cbf_visualize.py).

  1. prediction_on_T1.png      MELD lesion over conformed T1
  2. hipp_on_T1.png            HippUnfold subfields over T1, lesion contour in green
  3. hipp_with_pred.png        Subfields with lesion-focused axial slices

Usage:
  lesion_visualize.py <subject> <T1.mgz> <prediction.nii.gz> <hipp_subfields.nii.gz> <out_dir>
"""
from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")
import nibabel as nib
import numpy as np
from nilearn import image, plotting


def lesion_cut_coords(pred_img):
    """Center-of-mass (world mm) of nonzero prediction voxels, else None."""
    data = np.asarray(pred_img.get_fdata())
    mask = data > 0
    if not mask.any():
        return None
    ijk = np.array(np.where(mask)).mean(axis=1)
    xyz = nib.affines.apply_affine(pred_img.affine, ijk)
    return tuple(xyz)


def require_file(path, label):
    if not os.path.isfile(path):
        print(f"[viz][ERROR] missing {label}: {path}", file=sys.stderr)
        return False
    return True


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        return 1
    subject, t1_path, pred_path, hipp_path, out_dir = sys.argv[1:6]
    os.makedirs(out_dir, exist_ok=True)

    if not require_file(t1_path, "T1"):
        return 1

    written = []
    t1 = image.load_img(t1_path)
    has_pred = require_file(pred_path, "prediction")
    has_hipp = require_file(hipp_path, "hipp subfields")
    pred = image.load_img(pred_path) if has_pred else None
    cut = lesion_cut_coords(pred) if has_pred else None
    disp_mode = "ortho"

    if has_pred:
        out = os.path.join(out_dir, f"{subject}_prediction_on_T1.png")
        d = plotting.plot_roi(
            image.math_img("img > 0", img=pred), bg_img=t1,
            cut_coords=cut, display_mode=disp_mode, title=f"{subject}: MELD prediction",
            cmap="autumn", alpha=0.7, black_bg=True)
        d.savefig(out, dpi=150)
        d.close()
        written.append(out)
        print(f"[viz] wrote {out}")

    if has_hipp:
        hipp = image.load_img(hipp_path)
        hipp_roi = image.math_img("img > 0", img=hipp)
        out = os.path.join(out_dir, f"{subject}_hipp_on_T1.png")
        d = plotting.plot_roi(
            hipp_roi, bg_img=t1, cut_coords=cut, display_mode=disp_mode,
            title=f"{subject}: HippUnfold subfields in MELD space",
            cmap="gist_ncar", alpha=0.55, black_bg=True)
        if has_pred and cut is not None:
            d.add_contours(image.math_img("img > 0", img=pred),
                           levels=[0.5], colors="lime", linewidths=1.5)
        d.savefig(out, dpi=150)
        d.close()
        written.append(out)
        print(f"[viz] wrote {out}")

        if has_pred and cut is not None:
            out = os.path.join(out_dir, f"{subject}_hipp_with_pred.png")
            d = plotting.plot_roi(
                hipp_roi, bg_img=t1, display_mode="z", cut_coords=6,
                title=f"{subject}: subfields @ lesion", cmap="gist_ncar",
                alpha=0.55, black_bg=True)
            d.add_contours(image.math_img("img > 0", img=pred),
                           levels=[0.5], colors="lime", linewidths=1.5)
            d.savefig(out, dpi=150)
            d.close()
            written.append(out)
            print(f"[viz] wrote {out}")
    elif has_pred:
        print("[viz] no hipp_subfields — prediction figure only")

    if not written:
        print("[viz][ERROR] no figures produced", file=sys.stderr)
        return 1

    print(f"[viz] DONE: {len(written)} figure(s) in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
