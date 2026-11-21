"""Pipeline run context: resolved paths for a region."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path



from app.core.config import Settings, get_settings
from app.regions import RegionDefinition, get_region


@dataclass
class PipelineContext:
    region: RegionDefinition
    settings: Settings
    force: bool = False

    @classmethod
    def for_region(cls, region_id: str, force: bool = False, settings: Settings | None = None) -> "PipelineContext":
        return cls(region=get_region(region_id), settings=settings or get_settings(), force=force)

    @property
    def shared_raw(self) -> Path:
        """State-level downloads reusable by every region in the same state."""
        return self.settings.raw_dir / "shared" / f"state-{self.region.state_fips}"

    @property
    def region_raw(self) -> Path:
        return self.settings.raw_dir / self.region.region_id

    @property
    def processed(self) -> Path:
        return self.settings.processed_dir / self.region.region_id

