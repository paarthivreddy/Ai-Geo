"""PIN code index for O(1) lookups."""

import polars as pl
from typing import Optional, List
from collections import defaultdict

from geocare.domain.entities.geography import PincodeRecord, PincodeResolution


class PincodeIndex:
    """In-memory PIN code index with O(1) lookup."""

    def __init__(self):
        self.by_code: dict[str, PincodeRecord] = {}
        self.by_locality: dict[str, List[str]] = defaultdict(list)  # locality -> PIN codes
        self.by_district_state: dict[tuple[str, str], List[str]] = defaultdict(list)
        self._loaded = False

    def load(self, df: pl.DataFrame) -> None:
        """Build indexes from Polars DataFrame."""
        for row in df.iter_rows(named=True):
            code = row['pincode']
            record = PincodeRecord(
                pincode=code,
                office_name=row['office_name'],
                office_type=row['office_type'],
                delivery_status=row['delivery_status'],
                district=row['district'],
                state=row['state'],
                taluk=row.get('taluk'),
                circle=row.get('circle'),
                region=row.get('region'),
                division=row.get('division'),
                latitude=row.get('latitude'),
                longitude=row.get('longitude'),
                localities=row.get('localities', []),
            )

            self.by_code[code] = record

            # Reverse index: locality -> PINs
            for loc in row.get('localities', []):
                if loc:
                    self.by_locality[loc.strip().lower()].append(code)

            # District+State -> PINs
            key = (row['district'].lower(), row['state'].lower())
            self.by_district_state[key].append(code)

        self._loaded = True

    def resolve(self, pincode: str) -> Optional[PincodeResolution]:
        """Exact PIN lookup with validation."""
        if not self._validate_pincode(pincode):
            return None

        record = self.by_code.get(pincode)
        if not record:
            return None

        return PincodeResolution(
            pincode=record.pincode,
            district=record.district,
            state=record.state,
            taluk=record.taluk,
            latitude=record.latitude,
            longitude=record.longitude,
            confidence=100,
            source="india_post",
        )

    def reverse_lookup(
        self,
        locality: str,
        district: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[PincodeResolution]:
        """Find candidate PINs for a locality (with optional context)."""
        candidates = self.by_locality.get(locality.lower(), [])

        if district and state:
            context_key = (district.lower(), state.lower())
            context_pins = self.by_district_state.get(context_key, [])
            candidates = [c for c in candidates if c in context_pins]

        results = []
        for c in candidates:
            resolved = self.resolve(c)
            if resolved:
                results.append(resolved)
        return results

    def _validate_pincode(self, pincode: str) -> bool:
        """Validate Indian PIN code format."""
        import re
        return bool(re.match(r'^[1-8]\d{5}$', pincode))