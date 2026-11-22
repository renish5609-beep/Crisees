#!/usr/bin/env python3
"""Package processed data for deployment as an immutable, checksummed artifact.

    python scripts/package_data_release.py --region houston-sw-pilot

Writes dist/crisees-data-<region>-<stamp>.tar.gz plus a .sha256 file. Upload
both to a GitHub Release (or any static host) and set CRISEES_DATA_URL and
CRISEES_DATA_SHA256 on the backend. Only processed (derived/public) data is
included, with ATTRIBUTION.md; raw downloads are not redistributed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import time
from pathlib import Path

import _bootstrap  # noqa: F401

from app.core.config import get_settings

ATTRIBUTION = """# Crisees processed data: attribution and licences

Derived from public sources. See docs/DATA_SOURCES.md in the repository for details.

- U.S. Census Bureau: TIGER/Line 2024 and American Community Survey 2020-2024 5-year (public domain).
- CDC/ATSDR Social Vulnerability Index 2020 (public domain; cite CDC/ATSDR SVI).
- FEMA flood hazard data, DFIRM 48157C (public domain).
- Road network and facilities: Overture Maps Foundation (places: CDLA-Permissive-2.0;
  transportation derived from OpenStreetMap, (c) OpenStreetMap contributors, ODbL 1.0).
  The road tables are a Derivative Database under the ODbL and are provided under the ODbL.

Flood closures, capacities and demand participation used by Crisees are hypothetical and are not part of this data.
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="houston-sw-pilot")
    p.add_argument("--out", default="dist")
    args = p.parse_args()
    s = get_settings()
    src = s.processed_dir / args.region
    manifest = json.loads((src / "manifest.json").read_text())
    stamp = manifest["generated_at"].replace(":", "").replace("-", "")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"crisees-data-{args.region}-{stamp}.tar.gz"
    path = out / name
    with tarfile.open(path, "w:gz", compresslevel=9) as tar:
        for f in sorted(src.iterdir()):
            if f.suffix in (".parquet", ".json"):
                info = tar.gettarinfo(str(f), arcname=f"{args.region}/{f.name}")
                info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
                with f.open("rb") as fh:
                    tar.addfile(info, fh)
        data = ATTRIBUTION.encode()
        info = tarfile.TarInfo(f"{args.region}/ATTRIBUTION.md")
        info.size, info.mtime = len(data), 0
        tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    print(json.dumps({"artifact": str(path), "bytes": path.stat().st_size, "sha256": digest,
                      "data_generated_at": manifest["generated_at"], "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
