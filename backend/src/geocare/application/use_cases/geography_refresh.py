"""Geography data refresh use case."""

from typing import Optional, List
from uuid import UUID

from geocare.domain.ports.repositories import (
    PincodeRepository,
    LocalityRepository,
    CensusRepository,
    PostGISRepository,
    GeographyEnginePort,
)
from geocare.domain.entities.geography import PincodeRecord, LocalityRecord, CensusHierarchyRecord


class GeographyRefreshUseCase:
    """Use case for refreshing geography reference data."""

    def __init__(
        self,
        pincode_repo: PincodeRepository,
        locality_repo: LocalityRepository,
        census_repo: CensusRepository,
        postgis_repo: PostGISRepository,
        geography_engine: GeographyEnginePort,
    ):
        self.pincode_repo = pincode_repo
        self.locality_repo = locality_repo
        self.census_repo = census_repo
        self.postgis_repo = postgis_repo
        self.geography_engine = geography_engine

    async def refresh_all(
        self,
        pincode_csv_path: Optional[str] = None,
        locality_parquet_path: Optional[str] = None,
        census_csv_path: Optional[str] = None,
        osm_pbf_path: Optional[str] = None,
        version: str = "latest",
    ) -> dict:
        """Refresh all geography datasets."""
        results = {}

        if pincode_csv_path:
            results["pincode"] = await self.refresh_pincode(pincode_csv_path, version)

        if locality_parquet_path:
            results["locality"] = await self.refresh_locality(locality_parquet_path, version)

        if census_csv_path:
            results["census"] = await self.refresh_census(census_csv_path, version)

        if osm_pbf_path:
            results["osm"] = await self.refresh_osm(osm_pbf_path)

        # Rebuild in-memory indexes
        await self.geography_engine.rebuild_indexes()

        return results

    async def refresh_pincode(self, csv_path: str, version: str) -> dict:
        """Refresh PIN code directory from India Post CSV."""
        import polars as pl

        # Read and validate
        df = pl.read_csv(csv_path)
        required_cols = ["pincode", "office_name", "office_type", "delivery_status",
                         "district", "state", "taluk", "circle", "region", "division",
                         "latitude", "longitude", "localities"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        # Transform
        records = []
        for row in df.iter_rows(named=True):
            records.append(PincodeRecord(
                pincode=row["pincode"],
                office_name=row["office_name"],
                office_type=row["office_type"],
                delivery_status=row["delivery_status"],
                district=row["district"],
                state=row["state"],
                taluk=row.get("taluk"),
                circle=row.get("circle"),
                region=row.get("region"),
                division=row.get("division"),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
                localities=row.get("localities", "").split(",") if row.get("localities") else [],
                source_version=version,
            ))

        # Load
        await self.pincode_repo.truncate()
        await self.pincode_repo.load_batch(records)

        return {"loaded": len(records), "version": version}

    async def refresh_locality(self, parquet_path: str, version: str) -> dict:
        """Refresh locality dictionary from merged parquet."""
        import polars as pl

        df = pl.read_parquet(parquet_path)
        records = []

        for row in df.iter_rows(named=True):
            records.append(LocalityRecord(
                id=row["id"],
                canonical_name=row["canonical_name"],
                aliases=row.get("aliases", []),
                pincode=row["pincode"],
                city=row["city"],
                district=row["district"],
                state=row["state"],
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
                population=row.get("population"),
                source=row.get("source", "merged"),
                source_version=version,
            ))

        await self.locality_repo.truncate()
        await self.locality_repo.load_batch(records)

        return {"loaded": len(records), "version": version}

    async def refresh_census(self, csv_path: str, version: str) -> dict:
        """Refresh Census hierarchy."""
        import polars as pl

        df = pl.read_csv(csv_path)
        records = []

        for row in df.iter_rows(named=True):
            records.append(CensusHierarchyRecord(
                state_code=row["state_code"],
                state_name=row["state_name"],
                district_code=row.get("district_code"),
                district_name=row.get("district_name"),
                subdistrict_code=row.get("subdistrict_code"),
                subdistrict_name=row.get("subdistrict_name"),
                village_code=row.get("village_code"),
                village_name=row.get("village_name"),
                level=row["level"],
                population=row.get("population"),
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
            ))

        await self.census_repo.truncate()
        await self.census_repo.load_batch(records)

        return {"loaded": len(records), "version": version}

    async def refresh_osm(self, pbf_path: str) -> dict:
        """Refresh OSM boundaries via osm2pgsql."""
        import subprocess

        cmd = [
            "osm2pgsql",
            "--create",
            "--slim",
            "--flat-nodes", "/data/flat-nodes.bin",
            "--database", "postgresql://postgres:password@osm-db:5432/osm",
            "--hstore",
            "--tag-transform-script", "/scripts/style.lua",
            pbf_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            raise RuntimeError(f"osm2pgsql failed: {result.stderr}")

        # Refresh materialized views
        await self.postgis_repo.refresh_choropleth_views()

        return {"status": "completed", "output": result.stdout[:1000]}