"""Install a checksummed processed-data release (used by scripts and by the API
on serverless cold starts).

The archive is downloaded to a temporary directory, its SHA-256 verified, and
extracted next to the destination before an atomic rename. A marker file
records the installed checksum so repeated calls are no-ops.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path

from app.core.config import Settings

logger = logging.getLogger(__name__)
MARKER = ".release_sha256"
_lock = threading.Lock()


class ReleaseError(RuntimeError):
    pass


def installed(settings: Settings, region: str, sha256: str) -> bool:
    marker = settings.processed_dir / region / MARKER
    return marker.exists() and marker.read_text().strip() == sha256.lower()


def install_release(settings: Settings, region: str, url: str, sha256: str) -> Path:
    dest = settings.processed_dir / region
    with _lock:
        if installed(settings, region, sha256):
            return dest
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.data_dir) as tmp:
            archive = Path(tmp) / "release.tar.gz"
            logger.info("downloading data release %s", url)
            try:
                with urllib.request.urlopen(url, timeout=120) as r, archive.open("wb") as fh:  # noqa: S310 - operator-configured URL
                    shutil.copyfileobj(r, fh)
            except OSError as exc:
                raise ReleaseError(f"Could not download data release: {exc}") from exc
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if digest != sha256.lower():
                raise ReleaseError(f"Checksum mismatch: expected {sha256}, got {digest}")
            extract = Path(tmp) / "x"
            with tarfile.open(archive) as tar:
                members = [m for m in tar.getmembers() if m.isfile() and m.name.startswith(f"{region}/")
                           and ".." not in Path(m.name).parts and not Path(m.name).is_absolute()]
                tar.extractall(extract, members=members, filter="data")
            staged = extract / region
            if not (staged / "manifest.json").exists():
                raise ReleaseError("Archive has no manifest.json for this region")
            (staged / MARKER).write_text(sha256.lower())
            dest.parent.mkdir(parents=True, exist_ok=True)
            backup = dest.with_name(dest.name + ".old")
            if dest.exists():
                shutil.rmtree(backup, ignore_errors=True)
                dest.rename(backup)
            shutil.move(str(staged), str(dest))
            shutil.rmtree(backup, ignore_errors=True)
        logger.info("installed data release %s for %s", sha256[:12], region)
        return dest
