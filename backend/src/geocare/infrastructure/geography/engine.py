"""Geography engine main orchestrator."""

from typing import Optional, Dict, Any, List
from uuid import UUID

from geocare.domain.ports.geography import GeographyEnginePort
from geocare.domain.ports.repositories import (
    PincodeRepository,
    LocalityRepository,
    CensusRepository,
    PostGISRepository,
)
from geocare.domain.entities.geography import (
    PincodeResolution,
    LocalityMatch,
    GeoContext,
    EnrichmentResult,
    ParsedAddress,
    EnrichedAddress,
    ValidationResult,
)
from geocare.infrastructure.geography.pincode_index import PincodeIndex
from geocare.infrastructure.geography.locality_fuzzy import LocalityFuzzyIndex
from geocare.infrastructure.geography.census_hierarchy import CensusHierarchy
from geocare.infrastructure.geography.parser_adapter import LibpostalAdapter


class GeographyEngine(GeographyEnginePort):
    """Main geography enrichment orchestrator."""

    def __init__(
        self,
        pincode_index: PincodeIndex,
        locality_fuzzy: LocalityFuzzyIndex,
        census_hierarchy: CensusHierarchy,
        parser_adapter: LibpostalAdapter,
        postgis_repo: PostGISRepository,
    ):
        self.pincode_index = pincode_index
        self.locality_fuzzy = locality_fuzzy
        self.census_hierarchy = census_hierarchy
        self.parser_adapter = parser_adapter
        self.postgis_repo = postgis_repo

    async def enrich_address(
        self,
        address_input: Dict[str, Any],
        parsed_address: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Enrich address and return (enriched_address, confidence_score)."""
        # Build context from input
        context = GeoContext(
            pincode=address_input.get("pincode"),
            locality=address_input.get("locality"),
            city=address_input.get("city"),
            district=address_input.get("district"),
            state=address_input.get("state"),
            taluk=parsed_address.get("village"),
        )

        # 1. Resolve PIN code (highest confidence)
        pincode_result = None
        if context.pincode:
            pincode_result = self.pincode_index.resolve(context.pincode)
            if pincode_result:
                context = context.merge(pincode_result.to_context())

        # 2. Match locality with context
        locality_result = None
        if context.locality:
            matches = await self.locality_fuzzy.match(context.locality, context)
            if matches:
                locality_result = matches[0]
                context = context.merge(locality_result.to_context())

        # 3. Enrich hierarchy from PIN
        enrichment = None
        if pincode_result:
            enrichment = self.census_hierarchy.enrich_from_pincode(pincode_result.pincode)
            if enrichment:
                context = context.merge(GeoContext(
                    city=enrichment.cities[0] if enrichment.cities else None,
                    district=enrichment.district,
                    state=enrichment.state,
                    taluk=enrichment.taluk,
                ))

        # 4. Resolve remaining components
        city_result = self._resolve_city(parsed_address.get("city"), context)
        district_result = self._resolve_district(parsed_address.get("district"), context)
        state_result = self._resolve_state(parsed_address.get("state"), context)

        # 5. Build enriched address
        enriched = EnrichedAddress(
            line1=parsed_address.get("house_number", "") + " " + parsed_address.get("street", ""),
            line2=parsed_address.get("sublocality"),
            locality=locality_result.canonical_name if locality_result else parsed_address.get("locality"),
            city=city_result or parsed_address.get("city"),
            district=district_result or parsed_address.get("district"),
            state=state_result or parsed_address.get("state"),
            pincode=pincode_result.pincode if pincode_result else parsed_address.get("pincode"),
            country="India",
        )

        # 6. Validate with PostGIS
        validation = ValidationResult(valid=True, errors=[])
        if enriched.latitude and enriched.longitude:
            validation = await self.postgis_repo.validate_hierarchy(enriched)
            if not validation.valid:
                enriched = self._apply_corrections(enriched, validation)

        # 7. Calculate confidence
        confidence = self._calculate_confidence(
            pincode_result=pincode_result,
            locality_result=locality_result,
            validation=validation,
            parsed=parsed_address,
        )

        return enriched.to_dict(), confidence

    async def parse_address(self, text: str) -> Dict[str, Any]:
        """Parse raw address text into structured components."""
        return self.parser_adapter.parse(text)

    async def resolve_pincode(self, pincode: str) -> Optional[Dict[str, Any]]:
        """Resolve PIN code to district/state."""
        result = self.pincode_index.resolve(pincode)
        return result.to_dict() if result else None

    async def match_locality(self, name: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Match locality name with context."""
        geo_context = GeoContext(**(context or {}))
        matches = await self.locality_fuzzy.match(name, geo_context)
        return matches[0].to_dict() if matches else None

    def get_dataset_version(self) -> str:
        """Get current geography dataset version."""
        # Would track version from loaded data
        return "1.0.0"

    def _resolve_city(self, city: Optional[str], context: GeoContext) -> Optional[str]:
        if not city:
            return context.city
        # Fuzzy match city
        # For now return context
        return context.city

    def _resolve_district(self, district: Optional[str], context: GeoContext) -> Optional[str]:
        if not district:
            return context.district
        return context.district

    def _resolve_state(self, state: Optional[str], context: GeoContext) -> Optional[str]:
        if not state:
            return context.state
        return context.state

    def _apply_corrections(self, enriched: EnrichedAddress, validation: ValidationResult) -> EnrichedAddress:
        """Apply spatial corrections."""
        # Would correct city/district/state based on validation errors
        return enriched

    def _calculate_confidence(
        self,
        pincode_result: Optional[PincodeResolution],
        locality_result: Optional[LocalityMatch],
        validation: ValidationResult,
        parsed: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate weighted confidence score."""
        weights = {
            "pincode_validity": 0.25,
            "locality_match": 0.25,
            "hierarchy_consistency": 0.20,
            "parsing_completeness": 0.15,
            "fuzzy_quality": 0.15,
        }

        # PIN score
        pin_score = 100 if pincode_result and pincode_result.confidence == 100 else (50 if pincode_result else 0)

        # Locality score
        loc_score = locality_result.score if locality_result else 0

        # Hierarchy score
        hier_score = 100 if validation.valid else max(0, 100 - len(validation.errors) * 20)

        # Parsing completeness
        components = [
            parsed.get("house_number"),
            parsed.get("street"),
            parsed.get("locality"),
            parsed.get("city"),
            parsed.get("district"),
            parsed.get("state"),
            parsed.get("pincode"),
        ]
        parse_score = int((sum(1 for c in components if c) / len(components)) * 100)

        # Fuzzy quality
        fuzzy_score = loc_score  # Reuse locality match quality

        overall = int(
            weights["pincode_validity"] * pin_score +
            weights["locality_match"] * loc_score +
            weights["hierarchy_consistency"] * hier_score +
            weights["parsing_completeness"] * parse_score +
            weights["fuzzy_quality"] * fuzzy_score
        )

        # Determine tier
        if overall >= 85:
            tier = "high"
        elif overall >= 60:
            tier = "medium"
        elif overall >= 40:
            tier = "low"
        else:
            tier = "unverified"

        # Determine method
        if pin_score == 100 and loc_score == 100:
            method = "exact"
        elif loc_score > 0:
            method = "fuzzy"
        elif pin_score == 50:
            method = "inferred"
        else:
            method = "manual"

        return {
            "overall": overall,
            "pincode_validity": pin_score,
            "locality_match": loc_score,
            "hierarchy_consistency": hier_score,
            "parsing_completeness": parse_score,
            "fuzzy_quality": fuzzy_score,
            "method": method,
            "tier": tier,
        }