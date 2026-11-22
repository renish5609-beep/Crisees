"""Vercel build hook (pyproject [tool.vercel.scripts] build).

Runs after dependencies are installed and before the function is bundled.
Removes installed files the API never loads, to fit Vercel's 500 MB Python
function limit. Verified locally: every API endpoint runs from this trimmed
package set.

* pyogrio (+ bundled GDAL, ~100 MB): geopandas imports it lazily for
  read_file/to_file only; the API reads Parquet exclusively.
* test suites, C headers and Arrow Flight libraries.
"""

from __future__ import annotations

import glob
import os
import shutil
import site
import sys
import sysconfig

BUNDLE_DIR = "data_bundle"  # CRISEES_DATA_DIR on Vercel (relative to backend/)

TARGETS = [
    "pyogrio", "pyogrio.libs", "pyogrio-*.dist-info",
    # pyarrow is only needed to read Parquet; the bundle ships pickles instead.
    "pyarrow", "pyarrow-*.dist-info",
    # scipy subpackages the API never imports (it uses sparse, csgraph, spatial, optimize, linalg, special).
    "scipy/stats", "scipy/io", "scipy/signal", "scipy/interpolate", "scipy/integrate", "scipy/ndimage",
    "scipy/odr", "scipy/misc", "scipy/datasets", "scipy/cluster", "scipy/fftpack",
    "pandas/tests", "pyarrow/tests", "pyarrow/include", "scipy/*/tests", "scipy/*/*/tests",
    "numpy/*/tests", "networkx/*/tests", "shapely/tests",
    "pyarrow/libarrow_flight.so*", "pyarrow/_flight*.so",
]


def site_dirs() -> list[str]:
    """Only the project's own virtualenv on a Vercel build machine."""
    dirs = set(glob.glob(".vercel/python/.venv/lib/python*/site-packages"))
    prefix = os.path.realpath(".vercel/python/.venv")
    for d in {sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"], *site.getsitepackages()}:
        if os.path.realpath(d).startswith(prefix + os.sep):
            dirs.add(d)
    return sorted(d for d in dirs if os.path.isdir(d))


def size_mb(path: str) -> float:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total / 1e6


def bundle_data() -> None:
    """Install the checksum-verified data release and convert it to pickles
    (no pyarrow needed at runtime). Arrow-backed string columns become plain
    Python objects first so unpickling never imports pyarrow."""
    import gzip
    import pickle
    from pathlib import Path

    sys.path.insert(0, os.getcwd())
    import geopandas as gpd
    import pandas as pd

    from app.core.config import Settings
    from app.regions import load_regions
    from pipeline.release import install_release

    url, sha = os.environ.get("CRISEES_DATA_URL"), os.environ.get("CRISEES_DATA_SHA256")
    if not (url and sha):
        print("[crisees build] CRISEES_DATA_URL/SHA256 not set; no data bundled")
        return
    settings = Settings(data_dir=Path(BUNDLE_DIR).resolve())
    for region in load_regions():
        dest = install_release(settings, region, url, sha)
        total = 0
        for f in sorted(dest.glob("*.parquet")):
            try:
                df = gpd.read_parquet(f)
            except ValueError:  # no geometry column
                df = pd.read_parquet(f)
            for c in df.columns:
                if c != "geometry" and pd.api.types.is_string_dtype(df[c]) and df[c].dtype != object:
                    df[c] = df[c].astype(object)
            # pandas 3 also backs string *labels* with pyarrow.
            df.columns = pd.Index(list(df.columns), dtype=object)
            if pd.api.types.is_string_dtype(df.index) and df.index.dtype != object:
                df.index = pd.Index(list(df.index), dtype=object)
            payload = pickle.dumps(df, protocol=5)
            if b"pyarrow" in payload:
                raise SystemExit(f"[crisees build] {f.name}: pickle still references pyarrow; refusing to bundle")
            out = f.with_name(f.stem + ".pkl.gz")
            with gzip.open(out, "wb", compresslevel=6) as fh:
                fh.write(payload)
            total += out.stat().st_size
            f.unlink()
        print(f"[crisees build] bundled {region}: {total / 1e6:.1f} MB of pickled datasets in {dest}")


def main() -> None:
    if os.environ.get("VERCEL") != "1":
        print("[crisees build] not a Vercel build (VERCEL!=1); nothing pruned")
        return
    bundle_data()
    dirs = site_dirs()
    if not dirs:
        print("[crisees build] project virtualenv not found; nothing pruned")
    for sp in dirs:
        before = size_mb(sp)
        removed = []
        for pattern in TARGETS:
            for p in glob.glob(os.path.join(sp, pattern)):
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                removed.append(os.path.relpath(p, sp))
        print(f"[crisees build] {sp}: {before:.0f} MB -> {size_mb(sp):.0f} MB; removed {len(removed)} paths")


if __name__ == "__main__":
    main()
