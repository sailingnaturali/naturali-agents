from poseidon import mutes


def test_restricted_area_path_resolves_to_whale_zones():
    assert mutes.category_for_path(
        "navigation.restrictedArea.e7e2f870-f6b9-5851-819d-8de04be1f97a"
    ) == "whale-zones"


def test_unrelated_path_resolves_to_no_category():
    assert mutes.category_for_path("electrical.batteries.0.voltage") is None
