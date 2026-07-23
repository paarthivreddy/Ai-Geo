"""PostGIS repository implementation for spatial queries."""

from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.ports.repositories import PostGISRepository


class PostGISRepositoryImpl(PostGISRepository):
    """SQLAlchemy implementation of PostGISRepository using OSM database."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate_hierarchy(
        self,
        latitude: float,
        longitude: float,
        expected_city: Optional[str] = None,
        expected_district: Optional[str] = None,
        expected_state: Optional[str] = None,
    ) -> tuple[bool, List[str]]:
        """Validate address hierarchy via point-in-polygon."""
        errors = []

        point_wkt = f"POINT({longitude} {latitude})"

        query = text("""
            SELECT
                city.name as city_name,
                dist.name as district_name,
                state.name as state_name
            FROM osm.admin_boundaries city
            JOIN osm.admin_boundaries dist
                ON ST_Contains(dist.geom, city.geom)
                AND dist.admin_level = 6
            JOIN osm.admin_boundaries state
                ON ST_Contains(state.geom, dist.geom)
                AND state.admin_level = 4
            WHERE city.admin_level = 8
            AND ST_Contains(city.geom, ST_GeomFromText(:point, 4326))
        """)

        result = await self.session.execute(query, {"point": point_wkt})
        row = result.first()

        if not row:
            errors.append("No containing hierarchy found for coordinates")
            return False, errors

        if expected_city and expected_city.lower() != (row.city_name or "").lower():
            errors.append(f"City mismatch: expected '{expected_city}', found '{row.city_name}'")

        if expected_district and expected_district.lower() != (row.district_name or "").lower():
            errors.append(f"District mismatch: expected '{expected_district}', found '{row.district_name}'")

        if expected_state and expected_state.lower() != (row.state_name or "").lower():
            errors.append(f"State mismatch: expected '{expected_state}', found '{row.state_name}'")

        return len(errors) == 0, errors

    async def get_choropleth_data(
        self,
        job_id: UUID,
        level: str,  # "state" or "district"
    ) -> List[Dict[str, Any]]:
        """Get aggregated record counts by boundary for heatmap."""
        view_name = "state_boundaries" if level == "state" else "district_boundaries"

        query = text(f"""
            SELECT
                b.osm_id,
                b.name,
                b.name_en,
                b.geom,
                COUNT(r.id) as record_count
            FROM osm.{view_name} b
            JOIN patient_records r
                ON ST_Contains(b.geom, ST_Point(r.longitude, r.latitude))
            WHERE r.job_id = :job_id
            AND r.latitude IS NOT NULL
            AND r.longitude IS NOT NULL
            GROUP BY b.osm_id, b.name, b.name_en, b.geom
        """)

        result = await self.session.execute(query, {"job_id": str(job_id)})
        rows = result.mappings().all()

        return [
            {
                "osm_id": row["osm_id"],
                "name": row["name"],
                "name_en": row["name_en"],
                "record_count": row["record_count"],
            }
            for row in rows
        ]

    async def find_containing_boundary(
        self,
        latitude: float,
        longitude: float,
        admin_level: int,
    ) -> Optional[Dict[str, Any]]:
        """Find containing boundary at given admin level."""
        point_wkt = f"POINT({longitude} {latitude})"

        query = text("""
            SELECT osm_id, name, name_en, admin_level
            FROM osm.admin_boundaries
            WHERE admin_level = :level
            AND ST_Contains(geom, ST_GeomFromText(:point, 4326))
            ORDER BY ST_Area(geom) ASC
            LIMIT 1
        """)

        result = await self.session.execute(query, {"level": admin_level, "point": point_wkt})
        row = result.first()

        if not row:
            return None

        return {
            "osm_id": row.osm_id,
            "name": row.name,
            "name_en": row.name_en,
            "admin_level": row.admin_level,
        }

    async def refresh_choropleth_views(self) -> None:
        """Refresh materialized views for choropleth."""
        await self.session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY osm.state_boundaries"))
        await self.session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY osm.district_boundaries"))