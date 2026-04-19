from __future__ import annotations

from core.sector_map import get_sector, sector_count, can_add_to_sector


def test_known_symbols_map_to_correct_sector():
    assert get_sector("VCB") == "BANK"
    assert get_sector("HPG") == "STEEL"
    assert get_sector("VHM") == "REALESTATE"
    assert get_sector("FPT") == "TECH"
    assert get_sector("GAS") == "ENERGY"


def test_unknown_symbol_returns_other():
    assert get_sector("XYZ") == "OTHER"


def test_case_insensitive():
    assert get_sector("vcb") == get_sector("VCB")


def test_sector_count():
    counts = sector_count(["VCB", "ACB", "HPG"])
    assert counts["BANK"] == 2
    assert counts["STEEL"] == 1


def test_can_add_to_sector_allows_when_below_limit():
    # 1 bank already open, limit=2 → can add another bank
    assert can_add_to_sector("TCB", ["VCB"], max_per_sector=2) is True


def test_can_add_to_sector_blocks_when_at_limit():
    # 2 banks already open, limit=2 → cannot add third bank
    assert can_add_to_sector("TCB", ["VCB", "ACB"], max_per_sector=2) is False


def test_can_add_to_sector_allows_different_sector():
    # 2 banks open, adding a real estate symbol → allowed
    assert can_add_to_sector("VHM", ["VCB", "ACB"], max_per_sector=2) is True


def test_can_add_unknown_sector_always_allowed():
    # Symbol with no sector mapping → permissive
    assert can_add_to_sector("XYZ", ["XYZ", "XYZ"], max_per_sector=2) is True
