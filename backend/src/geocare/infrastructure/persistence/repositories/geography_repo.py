"""Geography reference data repositories."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from geocare.domain.entities.geography import (
    PincodeRecord,
    LocalityRecord,
    CensusHierarchyRecord,
)
from geocare.domain.ports.repositories import (
    PincodeRepository,
    LocalityRepository,
    CensusRepository,
)
from geocare.infrastructure.persistence.models import (
    PincodeDirectoryModel,
    LocalityDictionaryModel,
    CensusHierarchyModel,
)


class PincodeRepositoryImpl(PincodeRepository):
    """SQLAlchemy implementation of PincodeRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_batch(self, records: list[PincodeRecord]) -> None:
        models = [
            PincodeDirectoryModel(
                pincode=r.pincode,
                office_name=r.office_name,
                office_type=r.office_type,
                delivery_status=r.delivery_status,
                district=r.district,
                state=r.state,
                taluk=r.taluk,
                circle=r.circle,
                region=r.region,
                division=r.division,
                latitude=r.latitude,
                longitude=r.longitude,
                localities=r.localities,
                source_version=r.source_version,
            )
            for r in records
        ]
        self.session.add_all(models)
        await self.session.flush()

    async def get(self, pincode: str) -> Optional[PincodeRecord]:
        result = await self.session.execute(
            select(PincodeDirectoryModel).where(PincodeDirectoryModel.pincode == pincode)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def search_by_district_state(
        self, district: str, state: str
    ) -> list[PincodeRecord]:
        result = await self.session.execute(
            select(PincodeDirectoryModel)
            .where(
                PincodeDirectoryModel.district.ilike(district),
                PincodeDirectoryModel.state.ilike(state),
            )
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_localities_for_pincode(self, pincode: str) -> list[str]:
        result = await self.session.execute(
            select(PincodeDirectoryModel.localities).where(
                PincodeDirectoryModel.pincode == pincode
            )
        )
        row = result.scalar_one_or_none()
        return row or []

    async def count(self) -> int:
        result = await self.session.execute(
            select(func.count(PincodeDirectoryModel.pincode))
        )
        return result.scalar_one()

    async def truncate(self) -> None:
        await self.session.execute(PincodeDirectoryModel.__table__.delete())
        await self.session.flush()

    async def get_all(self) -> list[PincodeRecord]:
        result = await self.session.execute(select(PincodeDirectoryModel))
        return [self._to_entity(m) for m in result.scalars().all()]

    def _to_entity(self, model: PincodeDirectoryModel) -> PincodeRecord:
        return PincodeRecord(
            pincode=model.pincode,
            office_name=model.office_name,
            office_type=model.office_type,
            delivery_status=model.delivery_status,
            district=model.district,
            state=model.state,
            taluk=model.taluk,
            circle=model.circle,
            region=model.region,
            division=model.division,
            latitude=model.latitude,
            longitude=model.longitude,
            localities=model.localities or [],
            source_version=model.source_version,
        )


class LocalityRepositoryImpl(LocalityRepository):
    """SQLAlchemy implementation of LocalityRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_batch(self, records: list[LocalityRecord]) -> None:
        models = [
            LocalityDictionaryModel(
                canonical_name=r.canonical_name,
                aliases=r.aliases,
                pincode=r.pincode,
                city=r.city,
                district=r.district,
                state=r.state,
                latitude=r.latitude,
                longitude=r.longitude,
                population=r.population,
                source=r.source,
                source_version=r.source_version,
            )
            for r in records
        ]
        self.session.add_all(models)
        await self.session.flush()

    async def get_by_canonical(self, name: str) -> Optional[LocalityRecord]:
        result = await self.session.execute(
            select(LocalityDictionaryModel).where(
                LocalityDictionaryModel.canonical_name.ilike(name)
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def search_by_alias(self, alias: str) -> list[LocalityRecord]:
        result = await self.session.execute(
            select(LocalityDictionaryModel).where(
                LocalityDictionaryModel.aliases.any(alias)
            ).limit(50)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_by_pincode(self, pincode: str) -> list[LocalityRecord]:
        result = await self.session.execute(
            select(LocalityDictionaryModel).where(
                LocalityDictionaryModel.pincode == pincode
            )
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def search_by_city_district(
        self, city: str, district: str, state: str
    ) -> list[LocalityRecord]:
        result = await self.session.execute(
            select(LocalityDictionaryModel)
            .where(
                LocalityDictionaryModel.city.ilike(city),
                LocalityDictionaryModel.district.ilike(district),
                LocalityDictionaryModel.state.ilike(state),
            )
            .limit(100)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(self) -> int:
        result = await self.session.execute(
            select(func.count(LocalityDictionaryModel.id))
        )
        return result.scalar_one()

    async def truncate(self) -> None:
        await self.session.execute(LocalityDictionaryModel.__table__.delete())
        await self.session.flush()

    async def get_all(self) -> list[LocalityRecord]:
        result = await self.session.execute(select(LocalityDictionaryModel))
        return [self._to_entity(m) for m in result.scalars().all()]

    def _to_entity(self, model: LocalityDictionaryModel) -> LocalityRecord:
        return LocalityRecord(
            id=model.id,
            canonical_name=model.canonical_name,
            aliases=model.aliases or [],
            pincode=model.pincode,
            city=model.city,
            district=model.district,
            state=model.state,
            latitude=model.latitude,
            longitude=model.longitude,
            population=model.population,
            source=model.source,
            source_version=model.source_version,
        )


class CensusRepositoryImpl(CensusRepository):
    """SQLAlchemy implementation of CensusRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def load_batch(self, records: list[CensusHierarchyRecord]) -> None:
        models = [
            CensusHierarchyModel(
                state_code=r.state_code,
                state_name=r.state_name,
                district_code=r.district_code,
                district_name=r.district_name,
                subdistrict_code=r.subdistrict_code,
                subdistrict_name=r.subdistrict_name,
                village_code=r.village_code,
                village_name=r.village_name,
                level=r.level,
                population=r.population,
                latitude=r.latitude,
                longitude=r.longitude,
            )
            for r in records
        ]
        self.session.add_all(models)
        await self.session.flush()

    async def get_state(self, code: str) -> Optional[CensusHierarchyRecord]:
        result = await self.session.execute(
            select(CensusHierarchyModel)
            .where(
                CensusHierarchyModel.state_code == code,
                CensusHierarchyModel.level == "State",
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_district(self, code: str) -> Optional[CensusHierarchyRecord]:
        result = await self.session.execute(
            select(CensusHierarchyModel)
            .where(
                CensusHierarchyModel.district_code == code,
                CensusHierarchyModel.level == "District",
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_subdistrict(self, code: str) -> Optional[CensusHierarchyRecord]:
        result = await self.session.execute(
            select(CensusHierarchyModel)
            .where(
                CensusHierarchyModel.subdistrict_code == code,
                CensusHierarchyModel.level == "Sub-district",
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def search_by_name(
        self, name: str, level: Optional[str] = None
    ) -> list[CensusHierarchyRecord]:
        query = select(CensusHierarchyModel).where(
            CensusHierarchyModel.village_name.ilike(f"%{name}%")
        )
        if level:
            query = query.where(CensusHierarchyModel.level == level)
        query = query.limit(50)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_hierarchy_from_pincode(self, pincode: str) -> Optional[dict]:
        # This would require joining with pincode_directory to get state/district codes
        # For now, return None - implement with pincode join when needed
        return None

    async def truncate(self) -> None:
        await self.session.execute(CensusHierarchyModel.__table__.delete())
        await self.session.flush()

    async def get_all(self) -> list[CensusHierarchyRecord]:
        result = await self.session.execute(select(CensusHierarchyModel))
        return [self._to_entity(m) for m in result.scalars().all()]

    def _to_entity(self, model: CensusHierarchyModel) -> CensusHierarchyRecord:
        return CensusHierarchyRecord(
            state_code=model.state_code,
            state_name=model.state_name,
            district_code=model.district_code,
            district_name=model.district_name,
            subdistrict_code=model.subdistrict_code,
            subdistrict_name=model.subdistrict_name,
            village_code=model.village_code,
            village_name=model.village_name,
            level=model.level,
            population=model.population,
            latitude=model.latitude,
            longitude=model.longitude,
        )