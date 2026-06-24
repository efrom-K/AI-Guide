"""Map raw OSM tags to a coarse category + a 0..1 type weight.

The weight ranks *a priori* interestingness by type (museum/monument > shop),
later combined with proximity and gaze in ``ranking.py``.
"""

from __future__ import annotations

WEIGHT_BY_CATEGORY: dict[str, float] = {
    # landmarks / culture
    "museum": 0.9,
    "gallery": 0.9,
    "monument": 0.9,
    "memorial": 0.9,
    "castle": 0.9,
    "attraction": 0.85,
    "fort": 0.85,
    "ruins": 0.8,
    "archaeological_site": 0.8,
    "place_of_worship": 0.8,
    "historic": 0.75,
    "viewpoint": 0.6,
    "artwork": 0.6,
    "theatre": 0.6,
    "arts_centre": 0.6,
    "cinema": 0.55,
    # green & nature
    "nature_reserve": 0.7,
    "peak": 0.7,
    "waterfall": 0.75,
    "volcano": 0.85,
    "glacier": 0.8,
    "reservoir": 0.65,
    "water": 0.6,
    "river": 0.55,
    "spring": 0.6,
    "beach": 0.6,
    "bay": 0.6,
    "cliff": 0.6,
    "wetland": 0.5,
    "forest": 0.45,
    "wood": 0.45,
    "park": 0.5,
    "garden": 0.5,
    # notable structures
    "lighthouse": 0.8,
    "tower": 0.6,
    "bridge": 0.55,
    "windmill": 0.6,
    "watermill": 0.6,
    "obelisk": 0.6,
    "fountain": 0.45,
    # everyday / commercial
    "cafe": 0.3,
    "restaurant": 0.3,
    "bar": 0.3,
    "pub": 0.3,
    "fast_food": 0.25,
    "shop": 0.25,
    "building": 0.15,
    "place": 0.2,
}
DEFAULT_WEIGHT = 0.2

# tags worth keeping on the Place (used by enrichment later)
KEEP_TAGS = frozenset(
    {
        "name",
        "name:en",
        "wikidata",
        "wikipedia",
        "tourism",
        "historic",
        "amenity",
        "leisure",
        "natural",
        "water",
        "waterway",
        "landuse",
        "man_made",
        "shop",
        "building",
        "religion",
    }
)


def weight_for(category: str) -> float:
    return WEIGHT_BY_CATEGORY.get(category, DEFAULT_WEIGHT)


def classify(tags: dict[str, str]) -> tuple[str, float]:
    """Return (category, weight) for a set of OSM tags."""
    category = _category(tags)
    return category, weight_for(category)


def _category(t: dict[str, str]) -> str:
    tourism = t.get("tourism")
    if tourism in {"museum", "gallery"}:
        return tourism
    if tourism in {"attraction", "artwork", "viewpoint"}:
        return tourism

    historic = t.get("historic")
    if historic:
        if historic in {
            "monument",
            "memorial",
            "castle",
            "fort",
            "ruins",
            "archaeological_site",
        }:
            return historic
        return "historic"

    amenity = t.get("amenity")
    if amenity == "place_of_worship":
        return "place_of_worship"
    if amenity in {
        "theatre",
        "cinema",
        "arts_centre",
        "cafe",
        "restaurant",
        "bar",
        "pub",
        "fast_food",
    }:
        return amenity

    leisure = t.get("leisure")
    if leisure in {"park", "garden", "nature_reserve"}:
        return leisure

    # nature & water
    if t.get("landuse") == "reservoir" or t.get("water") == "reservoir":
        return "reservoir"
    natural = t.get("natural")
    if natural in {
        "water", "wood", "peak", "bay", "beach", "cape", "cliff",
        "spring", "waterfall", "volcano", "glacier", "wetland",
    }:
        return natural
    if "water" in t:
        return "water"
    waterway = t.get("waterway")
    if waterway in {"river", "canal", "waterfall", "dam"}:
        return "waterfall" if waterway == "waterfall" else "river"
    if t.get("landuse") == "forest":
        return "forest"

    man_made = t.get("man_made")
    if man_made in {"bridge", "tower", "lighthouse", "watermill", "windmill", "obelisk"}:
        return man_made
    if t.get("amenity") == "fountain":
        return "fountain"

    if "shop" in t:
        return "shop"
    if "building" in t:
        return "building"
    return "place"
