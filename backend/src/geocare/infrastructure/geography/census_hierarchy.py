"""Census hierarchy for administrative boundary enrichment."""

from collections import defaultdict
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from geocare.domain.entities.geography import CensusHierarchyRecord
from geocare.domain.ports.repositories import CensusRepository


@dataclass
class VillageNode:
    """Village/town node in hierarchy."""
    code: str
    name: str
    level: str
    population: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class SubdistrictNode:
    """Sub-district (Taluk/Tehsil) node."""
    code: str
    name: str
    villages: Dict[str, VillageNode] = field(default_factory=dict)

    def all_villages(self) -> List[VillageNode]:
        return list(self.villages.values())


@dataclass
class DistrictNode:
    """District node."""
    code: str
    name: str
    subdistricts: Dict[str, SubdistrictNode] = field(default_factory=dict)

    def all_villages(self) -> List[VillageNode]:
        villages = []
        for sd in self.subdistricts.values():
            villages.extend(sd.all_villages())
        return villages


@dataclass
class StateNode:
    """State node."""
    code: str
    name: str
    districts: Dict[str, DistrictNode] = field(default_factory=dict)


class CensusHierarchy:
    """State → District → Sub-district → Village hierarchy from Census data."""

    def __init__(self, repository: CensusRepository):
        self.repository = repository
        self.states: Dict[str, StateNode] = {}
        self.by_name: Dict[str, List[CensusHierarchyRecord]] = defaultdict(list)
        self._loaded = False

    async def load(self) -> None:
        """Load Census hierarchy from repository."""
        if self._loaded:
            return

        records = await self.repository.get_all()

        for row in records:
            state = self.states.setdefault(row.state_code, StateNode(
                code=row.state_code,
                name=row.state_name,
            ))

            if row.district_code:
                district = state.districts.setdefault(row.district_code, DistrictNode(
                    code=row.district_code,
                    name=row.district_name,
                ))

                if row.subdistrict_code:
                    subdistrict = district.subdistricts.setdefault(row.subdistrict_code, SubdistrictNode(
                        code=row.subdistrict_code,
                        name=row.subdistrict_name,
                    ))

                    if row.village_code:
                        subdistrict.villages[row.village_code] = VillageNode(
                            code=row.village_code,
                            name=row.village_name,
                            level=row.level,
                            population=row.population,
                            latitude=row.latitude,
                            longitude=row.longitude,
                        )

            # Name index for fuzzy lookup
            if row.state_name:
                self.by_name[row.state_name.lower()].append(row)
            if row.district_name:
                self.by_name[row.district_name.lower()].append(row)
            if row.subdistrict_name:
                self.by_name[row.subdistrict_name.lower()].append(row)
            if row.village_name:
                self.by_name[row.village_name.lower()].append(row)

        self._loaded = True

    async def enrich_from_pincode(self, pincode: str) -> Optional[Dict[str, Any]]:
        """Use PIN → (District, State) to walk hierarchy."""
        # This would need pincode_index to get district/state
        # For now return None - would be called with pincode_index
        return None

    def get_state(self, code: str) -> Optional[StateNode]:
        return self.states.get(code)

    def get_district(self, state_code: str, district_code: str) -> Optional[DistrictNode]:
        state = self.states.get(state_code)
        if not state:
            return None
        return state.districts.get(district_code)

    def search_by_name(self, name: str, level: Optional[str] = None) -> List[CensusHierarchyRecord]:
        """Search hierarchy by name."""
        results = self.by_name.get(name.lower(), [])
        if level:
            results = [r for r in results if r.level == level]
        return results

    def get_all_cities(self) -> List[str]:
        """Get all city/town names for fuzzy matching."""
        cities = []
        for state in self.states.values():
            for district in state.districts.values():
                for village in district.all_villages():
                    if village.level in ("Town", "City"):
                        cities.append(village.name)
        return cities