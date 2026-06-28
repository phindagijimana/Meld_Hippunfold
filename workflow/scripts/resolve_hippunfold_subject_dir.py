#!/usr/bin/env python3
"""Resolve HippUnfold BIDS-app subject output dir (handles ses-*/anat layout)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def resolve_hippunfold_subject_dir(hipp_out: Path, subject: str) -> Path:
    """Return the session (or flat) directory that contains anat/ with subfield segs."""
    hipp_out = hipp_out.resolve()
    nested = hipp_out / "hippunfold" / subject
    if nested.is_dir():
        for pat in (
            "*desc-subfields*dseg.nii.gz",
            "*desc-subfields*dseg.nii",
            "*desc-subfields_dseg.nii.gz",
        ):
            for seg in sorted(nested.rglob(pat)):
                anat = seg.parent
                if anat.name == "anat" and anat.is_dir():
                    return anat.parent
        for ses in sorted(p for p in nested.iterdir() if p.is_dir()):
            if (ses / "anat").is_dir():
                return ses
        raise FileNotFoundError(
            f"No HippUnfold anat output for {subject} under {nested}"
        )

    flat = hipp_out / subject
    if (flat / "anat").is_dir():
        return flat
    raise FileNotFoundError(
        f"No HippUnfold output for {subject} under {hipp_out} "
        "(expected hippunfold/{subject}/ses-*/anat or {subject}/anat)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hipp_out", type=Path)
    parser.add_argument("subject")
    args = parser.parse_args()
    try:
        print(resolve_hippunfold_subject_dir(args.hipp_out, args.subject))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
