"""TIGER/Line census tract boundaries."""

from __future__ import annotations

from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import download_file
from pipeline.sources import catalog


def tract_zip_path(ctx: PipelineContext) -> Path:
    r = ctx.region
    return ctx.shared_raw / "tiger" / f"tl_{r.tiger_year}_{r.state_fips}_tract.zip"


def download_tracts(ctx: PipelineContext) -> Path:
    src = catalog.tiger_tracts(ctx.region.tiger_year, ctx.region.state_fips)
    return download_file(src["url"], tract_zip_path(ctx), force=ctx.force, expect_prefix=b"PK", source=src)
