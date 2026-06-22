import math

from app.shared.geo_math import angle_diff, bearing_deg, haversine_m
from app.shared.schemas import GeoPoint


def test_haversine_known_distance():
    # ~111.2 km per degree of latitude
    a = GeoPoint(lat=55.0, lon=37.0)
    b = GeoPoint(lat=56.0, lon=37.0)
    assert math.isclose(haversine_m(a, b), 111_195, rel_tol=0.01)


def test_haversine_zero():
    a = GeoPoint(lat=55.75, lon=37.62)
    assert haversine_m(a, a) == 0.0


def test_bearing_cardinal():
    origin = GeoPoint(lat=55.0, lon=37.0)
    north = GeoPoint(lat=55.5, lon=37.0)
    east = GeoPoint(lat=55.0, lon=37.5)
    assert math.isclose(bearing_deg(origin, north), 0.0, abs_tol=1.0)
    assert math.isclose(bearing_deg(origin, east), 90.0, abs_tol=1.0)


def test_angle_diff_wraps():
    assert angle_diff(10, 350) == 20
    assert angle_diff(0, 180) == 180
    assert angle_diff(90, 90) == 0
