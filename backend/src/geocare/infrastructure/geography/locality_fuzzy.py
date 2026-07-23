"""Locality fuzzy matching with BK-Tree and RapidFuzz."""

import re
import rapidfuzz
from rapidfuzz import fuzz, process
from typing import Optional, List, Dict, Set
from collections import defaultdict
from dataclasses import dataclass

from geocare.domain.entities.geography import LocalityRecord, LocalityMatch, GeoContext
from geocare.domain.ports.repositories import LocalityRepository


class TrieNode:
    """Trie node for prefix matching."""

    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.is_end: bool = False
        self.values: List[str] = []


class Trie:
    """Trie for prefix matching."""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str):
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.values.append(word)

    def prefix_search(self, prefix: str) -> Set[str]:
        """Find all words starting with prefix."""
        node = self.root
        for char in prefix:
            if char not in node.children:
                return set()
            node = node.children[char]

        results = set()
        self._collect(node, results)
        return results

    def _collect(self, node: TrieNode, results: Set[str]):
        if node.is_end:
            results.update(node.values)
        for child in node.children.values():
            self._collect(child, results)


class BKTree:
    """BK-Tree for Levenshtein distance search."""

    def __init__(self, distance_func=None):
        self.distance_func = distance_func or self._levenshtein
        self.tree = None

    def _levenshtein(self, s1: str, s2: str) -> int:
        """Levenshtein distance."""
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def add(self, word: str):
        if self.tree is None:
            self.tree = (word, {})
            return

        node = self.tree
        while True:
            parent_word, children = node
            distance = self.distance_func(word, parent_word)
            if distance in children:
                node = children[distance]
            else:
                children[distance] = (word, {})
                break

    def search(self, word: str, max_dist: int) -> Set[str]:
        """Search for words within max_dist."""
        if self.tree is None:
            return set()

        results = set()
        self._search_recursive(self.tree, word, max_dist, results)
        return results

    def _search_recursive(self, node, word: str, max_dist: int, results: Set[str]):
        parent_word, children = node
        distance = self.distance_func(word, parent_word)

        if distance <= max_dist:
            results.add(parent_word)

        for d in range(max(1, distance - max_dist), distance + max_dist + 1):
            if d in children:
                self._search_recursive(children[d], word, max_dist, results)


class RedisFuzzyCache:
    """Redis cache for fuzzy match results."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import redis.asyncio as redis
            self._client = redis.from_url(self.redis_url)
        return self._client

    async def get(self, key: str) -> Optional[List[LocalityMatch]]:
        import json
        data = await self.client.get(key)
        if data:
            return [LocalityMatch(**item) for item in json.loads(data)]
        return None

    async def set(self, key: str, value: List[LocalityMatch], ttl: int = 86400):
        import json
        await self.client.setex(key, ttl, json.dumps([m.to_dict() for m in value]))


class LocalityFuzzyIndex:
    """Multi-strategy locality matching with context awareness."""

    def __init__(
        self,
        repository: LocalityRepository,
        threshold: int = 85,
        redis_url: str = "redis://localhost:6379/0",
    ):
        self.repository = repository
        self.threshold = threshold
        self.trie = Trie()
        self.bk_tree = BKTree()
        self.canonical: Dict[str, LocalityRecord] = {}
        self.aliases: Dict[str, str] = {}
        self.redis_cache = RedisFuzzyCache()
        self._loaded = False

    async def load(self) -> None:
        """Load localities from repository."""
        if self._loaded:
            return

        records = await self.repository.get_all()

        for record in records:
            canon = record.canonical_name.lower()
            self.canonical[canon] = record
            self.trie.insert(canon)
            self.bk_tree.add(canon)

            for alias in record.aliases:
                self.aliases[alias.lower()] = canon

        self._loaded = True

    async def match(
        self,
        query: str,
        context: Optional[GeoContext] = None,
        limit: int = 10,
    ) -> List[LocalityMatch]:
        """Match locality with multi-strategy search."""
        if not self._loaded:
            await self.load()

        query_lower = query.lower().strip()

        # Check cache first
        cache_key = f"fuzzy:{hash(query_lower + str(context))}"
        cached = await self.redis_cache.get(cache_key)
        if cached:
            return cached[:limit]

        candidates = set()

        # 1. Exact alias match
        if query_lower in self.aliases:
            candidates.add(self.aliases[query_lower])

        # 2. Exact canonical match
        if query_lower in self.canonical:
            candidates.add(query_lower)

        # 3. Prefix match (Trie)
        candidates.update(self.trie.prefix_search(query_lower))

        # 4. Fuzzy match (BK-Tree)
        bk_candidates = self.bk_tree.search(query_lower, max_dist=2)
        candidates.update(bk_candidates)

        # 5. RapidFuzz token-set ratio
        rf_candidates = process.extract(
            query_lower,
            self.canonical.keys(),
            scorer=fuzz.token_set_ratio,
            score_cutoff=self.threshold,
            limit=50,
        )
        candidates.update(c for c, s, _ in rf_candidates)

        # Rank with context
        results = []
        for canon in candidates:
            record = self.canonical[canon]
            score = self._calculate_score(query_lower, record, context)
            if score >= self.threshold:
                results.append(LocalityMatch(
                    canonical_name=record.canonical_name,
                    pincode=record.pincode,
                    city=record.city,
                    district=record.district,
                    state=record.state,
                    score=score,
                    method=self._determine_method(query_lower, record),
                    source=record.source,
                    latitude=record.latitude,
                    longitude=record.longitude,
                ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        # Cache top results
        await self.redis_cache.set(cache_key, results[:10])

        return results[:limit]

    def _calculate_score(
        self,
        query: str,
        record: LocalityRecord,
        context: Optional[GeoContext],
    ) -> int:
        """Calculate match score with context boost."""
        base = fuzz.token_set_ratio(query, record.canonical_name.lower())

        if context:
            # PIN code boost
            if context.pincode and context.pincode == record.pincode:
                base = min(100, base + 15)

            # District boost
            if context.district and context.district.lower() == record.district.lower():
                base = min(100, base + 10)

            # State boost
            if context.state and context.state.lower() == record.state.lower():
                base = min(100, base + 5)

        # Population weight
        if record.population and record.population > 100000:
            base = min(100, base + 3)

        return base

    def _determine_method(self, query: str, record: LocalityRecord) -> str:
        """Determine match method."""
        if query == record.canonical_name.lower():
            return "exact"
        if query in self.aliases and self.aliases[query] == record.canonical_name.lower():
            return "exact_alias"
        if record.canonical_name.lower().startswith(query):
            return "prefix"
        return "fuzzy"