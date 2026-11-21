"""Static source attribution metadata for every upstream dataset."""

from __future__ import annotations

from typing import Any


def tiger_tracts(year: int, state_fips: str) -> dict[str, Any]:
    return {
        "source_id": f"tiger-{year}-tract-{state_fips}",
        "name": f"TIGER/Line Shapefiles {year}: Census Tracts (state {state_fips})",
        "publisher": "U.S. Census Bureau",
        "url": f"https://www2.census.gov/geo/tiger/TIGER{year}/TRACT/tl_{year}_{state_fips}_tract.zip",
        "license": "Public domain (U.S. Government work)",
        "vintage": f"{year} (2020 Census tract definitions)",
    }


def acs5(year: int, method: str) -> dict[str, Any]:
    return {
        "source_id": f"acs5-{year}",
        "name": f"American Community Survey {year - 4}-{year} 5-year estimates",
        "publisher": "U.S. Census Bureau",
        "url": (
            f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/5YRData/"
            if method == "summary_file"
            else f"https://api.census.gov/data/{year}/acs/acs5"
        ),
        "license": "Public domain (U.S. Government work)",
        "vintage": f"{year - 4}-{year}",
        "notes": f"Tables B01003, B01001, B08201, C17002, C18108; retrieved via {method}.",
    }


SVI_CDC_2022 = {
    "source_id": "cdc-svi-2022",
    "name": "CDC/ATSDR Social Vulnerability Index 2022 (Texas, census tracts)",
    "publisher": "Centers for Disease Control and Prevention / ATSDR",
    "url": "https://svi.cdc.gov/Documents/Data/2022/csv/states/Texas.csv",
    "license": "Public domain; cite CDC/ATSDR SVI",
    "vintage": "2022 (ACS 2018-2022)",
}

SVI_ESRI_MIRROR_2020 = {
    "source_id": "cdc-svi-2020-esri-mirror",
    "name": "CDC/ATSDR Social Vulnerability Index 2020 (tracts), ArcGIS Online copy",
    "publisher": "CDC/ATSDR (data); hosted by Esri / ArcGIS Online",
    "url": "https://services1.arcgis.com/gGHDlz6USftL5Pau/ArcGIS/rest/services/CDC_Social_Vulnerability_Index_Tracts_2020/FeatureServer/1",
    "license": "Public domain; cite CDC/ATSDR SVI",
    "vintage": "2020 (ACS 2016-2020), US-wide percentile ranking",
    "notes": "Third-party mirror used because svi.cdc.gov / onemap.cdc.gov were unreachable. Attribute values "
    "are CDC's published SVI 2020 fields.",
}

FEMA_NFHL_OFFICIAL = {
    "source_id": "fema-nfhl",
    "name": "FEMA National Flood Hazard Layer (S_FLD_HAZ_AR, S_FIRM_PAN)",
    "publisher": "Federal Emergency Management Agency",
    "url": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
    "license": "Public domain (U.S. Government work)",
    "vintage": "Effective NFHL at retrieval time",
}

FEMA_FIRM_MIRROR_FORT_BEND = {
    "source_id": "fema-firm-48157C-mirror",
    "name": "FEMA FIRM Database, DFIRM 48157C (Fort Bend County, TX), ArcGIS Online copy",
    "publisher": "FEMA (data); hosted on ArcGIS Online by a third party",
    "url": "https://services1.arcgis.com/cTNi34MxOdcfum3A/ArcGIS/rest/services/Map_TX_WFL1/FeatureServer",
    "license": "Public domain (U.S. Government work)",
    "vintage": "Unverified; VERSION_ID values 1.1.1.0 / 2.3.3.x in the data",
    "notes": "Fallback used because hazards.fema.gov was unreachable. Covers Fort Bend County panels only; "
    "Harris County (48201C) is NOT included. Effective status not independently verified.",
}

OSM_OVERPASS = {
    "source_id": "osm-overpass",
    "name": "OpenStreetMap via Overpass API (OSMnx)",
    "publisher": "OpenStreetMap contributors",
    "url": "https://www.openstreetmap.org/copyright",
    "license": "ODbL 1.0",
}


def overture(release: str, theme: str) -> dict[str, Any]:
    lic = "ODbL 1.0 (OpenStreetMap-derived)" if theme == "transportation" else "CDLA-Permissive-2.0 (places)"
    return {
        "source_id": f"overture-{release}-{theme}",
        "name": f"Overture Maps Foundation release {release}, theme={theme}",
        "publisher": "Overture Maps Foundation" + ("; OpenStreetMap contributors" if theme == "transportation" else ""),
        "url": f"s3://overturemaps-us-west-2/release/{release}/theme={theme}/",
        "license": lic,
        "vintage": release,
    }
