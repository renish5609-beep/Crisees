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
import sysconfig

TARGETS = [
    "pyogrio", "pyogrio.libs", "pyogrio-*.dist-info",
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


def main() -> None:
    if os.environ.get("VERCEL") != "1":
        print("[crisees build] not a Vercel build (VERCEL!=1); nothing pruned")
        return
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
