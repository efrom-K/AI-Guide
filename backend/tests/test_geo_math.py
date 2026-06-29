import math

from app.shared.geo_math import angle_diff, bearing_deg, haversine_m, relative_bearing
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


def test_relative_bearing_signs_left_and_right():
    # facing north (0): due east is +90 (right), due west is -90 (left)
    assert math.isclose(relative_bearing(0, 90), 90.0, abs_tol=0.01)
    assert math.isclose(relative_bearing(0, 270), -90.0, abs_tol=0.01)
    # straight ahead and directly behind
    assert math.isclose(relative_bearing(40, 40), 0.0, abs_tol=0.01)
    assert abs(relative_bearing(0, 180)) == 180.0
    # wrap-around: facing 350, target 10 is 20° to the right
    assert math.isclose(relative_bearing(350, 10), 20.0, abs_tol=0.01)
