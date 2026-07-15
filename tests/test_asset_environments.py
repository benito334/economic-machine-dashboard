"""Assets-by-Environment reference page."""
from dashboard import asset_environments as ae
from dashboard import charting as c


def test_routed_in_reference():
    assert "/asset-environments" in c._PAGE_MAP


def test_layout_renders():
    lay = ae.get_layout()
    assert type(lay).__name__ == "Div"


def test_four_quadrants_and_badges_present():
    # 2x2 matrix: all four environments defined, each with assets + G/I badges.
    assert set(ae._QUADRANTS) == {"stag", "refl", "defl", "gold"}
    for q in ae._QUADRANTS.values():
        assert q["assets"]
        for _name, driver in q["assets"]:
            assert driver in ("G", "I")


def test_example_placement_matches_request():
    # The user's example: Rising Growth + Falling Inflation → Equities (G).
    gold = ae._QUADRANTS["gold"]
    assert "Rising growth" in gold["growth"] and "Falling inflation" in gold["infl"]
    assert ("Equities", "G") in gold["assets"]


def test_driver_table_covers_all_buckets():
    names = [row[0] for row in ae._RAY_TABLE]
    for key in ["Equities", "TIPS", "Commodities", "Gold", "REITs", "currencies", "Crypto"]:
        assert any(key.lower() in n.lower() for n in names), key
    # every cell is a (verdict, reason) pair
    for row in ae._RAY_TABLE:
        for verdict, reason in row[1:]:
            assert verdict in ("Stronger", "Weaker", "Mixed") and reason
