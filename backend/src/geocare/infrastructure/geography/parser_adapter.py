"""libpostal address parser adapter."""

import os
import re
from typing import Optional, Dict, Any

try:
    import postal.parser
    import postal.expand
    LIBPOSTAL_AVAILABLE = True
except ImportError:
    LIBPOSTAL_AVAILABLE = False
    postal = None

from geocare.domain.value_objects.address import ParsedAddress


class LibpostalAdapter:
    """Wrapper around libpostal with India-specific enhancements."""

    def __init__(self, data_dir: Optional[str] = None):
        if not LIBPOSTAL_AVAILABLE:
            raise RuntimeError("libpostal not available. Install python-postal and libpostal.")

        if data_dir:
            os.environ['LIBPOSTAL_DATA_DIR'] = data_dir

        self.parser = postal.parser
        self.expand = postal.expand

        # India-specific abbreviation expansions
        self.abbreviations = {
            r'\bRd\b': 'Road',
            r'\bSt\b': 'Street',
            r'\bAve\b': 'Avenue',
            r'\bBlvd\b': 'Boulevard',
            r'\bDr\b': 'Drive',
            r'\bLn\b': 'Lane',
            r'\bCt\b': 'Court',
            r'\bPl\b': 'Place',
            r'\bSq\b': 'Square',
            r'\bNgr\b': 'Nagar',
            r'\bClny\b': 'Colony',
            r'\bExtn\b': 'Extension',
            r'\bSec\b': 'Sector',
            r'\bBlk\b': 'Block',
            r'\bPh\b': 'Phase',
            r'\bAppt\b': 'Apartment',
            r'\bFlr\b': 'Floor',
            r'\bBldg\b': 'Building',
            r'\bNr\b': 'Near',
            r'\bOpp\b': 'Opposite',
            r'\bB/h\b': 'Behind',
            r'\bNr\b': 'Near',
            r'\bP\b': 'Plot',
            r'\bH\b': 'House',
            r'\bNo\b': 'Number',
        }

    def parse(self, address: str) -> ParsedAddress:
        """Parse address with libpostal and map to domain model."""
        if not address:
            return ParsedAddress()

        # Pre-process: expand abbreviations
        expanded = self._expand_abbreviations(address)

        # Parse with libpostal
        parsed = self.parser.parse_address(expanded)

        # Map libpostal labels to our domain
        components = {label: value for value, label in parsed}

        # Extract PIN code (libpostal may not catch it if at end)
        pincode = self._extract_pincode(address)
        if not pincode:
            pincode = components.get('postcode')

        return ParsedAddress(
            house_number=components.get('house_number') or components.get('house'),
            street=components.get('road') or components.get('street'),
            locality=components.get('suburb') or components.get('neighbourhood'),
            sublocality=components.get('suburb'),
            village=components.get('village'),
            city=components.get('city') or components.get('town'),
            district=components.get('state_district') or components.get('district'),
            state=components.get('state'),
            pincode=pincode,
            country=components.get('country', 'India'),
        )

    def _expand_abbreviations(self, text: str) -> str:
        """Expand common Indian address abbreviations."""
        for pattern, replacement in self.abbreviations.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _extract_pincode(self, text: str) -> Optional[str]:
        """Extract 6-digit Indian PIN code from text."""
        matches = re.findall(r'\b[1-8]\d{5}\b', text)
        return matches[-1] if matches else None

    def expand_address(self, address: str) -> list[str]:
        """Generate address variations for better matching."""
        return self.expand.expand_address(address)