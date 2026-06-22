from app.services.geo.ranking import build_candidates
from app.shared.schemas import GazeConfidence, GeoPoint, Heading, Place


def _place(pid: str, name: str, category: str, lat: float, lon: float) -> Place:
    return Place(id=pid, name=name, category=category, location=GeoPoint(lat=lat, lon=lon))


POSITION = GeoPoint(lat=55.7537, lon=37.6205)
PLACES = [
    _place("p_museum", "Museum", "museum", 55.7553, 37.6178),
    _place("p_shop", "Shop", "shop", 55.7538, 37.6206),  # very close, low weight
    _place("p_far", "Far church", "place_of_worship", 55.9000, 37.9000),  # out of radius
]


def test_radius_filters_far_places():
    cands = build_candidates(POSITION, Heading(), PLACES, radius_m=300.0)
    ids = {c.place.id for c in cands}
    assert "p_far" not in ids
    assert {"p_museum", "p_shop"} <= ids


def test_seen_are_excluded():
    cands = build_candidates(POSITION, Heading(), PLACES, radius_m=300.0, seen=["p_museum"])
    assert all(c.place.id != "p_museum" for c in cands)


def test_high_weight_can_outrank_closer_low_weight():
    # museum is farther but far more interesting than an adjacent shop
    cands = build_candidates(POSITION, Heading(), PLACES, radius_m=400.0)
    assert cands[0].place.id == "p_museum"


def test_gaze_cone_detected_when_heading_known():
    # heading roughly toward the museum (north-west)
    heading = Heading(direction_deg=330.0, gaze_confidence=GazeConfidence.HIGH)
    cands = build_candidates(POSITION, heading, PLACES, radius_m=400.0)
    museum = next(c for c in cands if c.place.id == "p_museum")
    assert museum.in_gaze_cone is True
    assert museum.gaze_confidence is GazeConfidence.HIGH
