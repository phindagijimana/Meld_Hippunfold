#!/usr/bin/env python3
"""Resample HippUnfold subfield segmentations into MELD prediction T1w grid."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from resolve_hippunfold_subject_dir import resolve_hippunfold_subject_dir


def _find_subfield_segs(hipp_subject_dir: Path) -> list[Path]:
    anat = hipp_subject_dir / "anat"
    if not anat.is_dir():
        raise FileNotFoundError(f"HippUnfold anat dir missing: {anat}")
    # HippUnfold v2+ uses e.g. *_desc-subfields_atlas-multihist7_dseg.nii.gz
    patterns = [
        "*hemi-*_space-T1w_desc-subfields*dseg.nii.gz",
        "*hemi-*_space-T1w_desc-subfields*dseg.nii",
        "*space-T1w*desc-subfields*dseg.nii.gz",
        "*space-cropT1w*desc-subfields*dseg.nii.gz",
        "*desc-subfields*dseg.nii.gz",
    ]
    found: list[Path] = []
    for pat in patterns:
        found.extend(sorted(anat.glob(pat)))
        if found:
            break
    # de-dupe while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    if not unique:
        raise FileNotFoundError(
            f"No HippUnfold subfield dseg under {anat} "
            "(expected *space-T1w*desc-subfields*dseg.nii.gz; "
            "run HippUnfold with --output_spaces T1w)"
        )
    return unique


def _combine_hemi_labels(paths: list[Path]) -> nib.Nifti1Image:
    combined_data: np.ndarray | None = None
    affine = None
    header = None
    for p in paths:
        img = nib.load(str(p))
        data = np.asanyarray(img.dataobj)
        if combined_data is None:
            combined_data = np.zeros_like(data, dtype=np.int32)
            affine = img.affine
            header = img.header.copy()
        if data.shape != combined_data.shape:
            # different hemi grids: resample each to first before max
            ref = nib.Nifti1Image(combined_data, affine, header)
            img = resample_from_to(img, ref, order=0)
            data = np.asanyarray(img.dataobj)
        combined_data = np.maximum(combined_data, data.astype(np.int32))
    assert combined_data is not None and affine is not None and header is not None
    return nib.Nifti1Image(combined_data, affine, header)


def fuse(
    meld_prediction: Path,
    hipp_subject_dir: Path,
    out_dir: Path,
    subject: str,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_path = meld_prediction
    if not ref_path.is_file():
        raise FileNotFoundError(f"MELD prediction not found: {ref_path}")

    seg_paths = _find_subfield_segs(hipp_subject_dir)
    hipp_native = _combine_hemi_labels(seg_paths)

    ref_img = nib.load(str(ref_path))
    resampled = resample_from_to(hipp_native, ref_img, order=0)
    data = np.asanyarray(resampled.dataobj).astype(np.int32)
    resampled = nib.Nifti1Image(data, ref_img.affine, ref_img.header)

    out_hipp = out_dir / "hipp_subfields_in_meld_space.nii.gz"
    out_meld = out_dir / "meld_prediction_ref.nii.gz"
    out_manifest = out_dir / "fusion_manifest.json"

    nib.save(resampled, str(out_hipp))
    if out_meld.resolve() != ref_path.resolve():
        nib.save(ref_img, str(out_meld))

    manifest = {
        "subject": subject,
        "meld_prediction": str(ref_path.resolve()),
        "hippunfold_subject_dir": str(hipp_subject_dir.resolve()),
        "hippunfold_source_segs": [str(p.resolve()) for p in seg_paths],
        "fused_subfields": str(out_hipp.resolve()),
        "meld_prediction_copy": str(out_meld.resolve()),
        "reference_space": "meld_prediction_nifti_grid",
        "resample_order": 0,
        "meld_shape": list(ref_img.shape),
        "hipp_combined_shape_before_resample": list(hipp_native.shape),
    }
    out_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--meld-prediction", type=Path, required=True)
    parser.add_argument(
        "--hippunfold-out",
        type=Path,
        required=True,
        help="HippUnfold BIDS-app output root (contains hippunfold/sub-*/ses-*/anat/)",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        hipp_dir = resolve_hippunfold_subject_dir(args.hippunfold_out, args.subject)
        fuse(
            args.meld_prediction,
            hipp_dir,
            args.out_dir,
            args.subject,
        )
    except Exception as exc:
        print(f"fuse_hippunfold_to_meld: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
