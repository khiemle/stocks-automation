"""
VN30 sector mapping — dùng cho portfolio-level concentration limit.

Mỗi symbol thuộc đúng 1 sector. Symbols không có trong map → sector "OTHER".
"""
from __future__ import annotations

_VN30_SECTOR_MAP: dict[str, str] = {
    # Banks (Ngân hàng)
    "ACB": "BANK",
    "BID": "BANK",
    "CTG": "BANK",
    "HDB": "BANK",
    "MBB": "BANK",
    "STB": "BANK",
    "TCB": "BANK",
    "TPB": "BANK",
    "VCB": "BANK",
    "VIB": "BANK",
    "VPB": "BANK",
    # Real estate (Bất động sản)
    "BCM": "REALESTATE",
    "NVL": "REALESTATE",
    "PDR": "REALESTATE",
    "VHM": "REALESTATE",
    "VIC": "REALESTATE",
    "VRE": "REALESTATE",
    # Oil & Gas / Energy (Năng lượng)
    "GAS": "ENERGY",
    "PLX": "ENERGY",
    "POW": "ENERGY",
    # Steel / Industrial (Thép / Công nghiệp)
    "HPG": "STEEL",
    # Consumer / Retail (Hàng tiêu dùng)
    "MWG": "CONSUMER",
    "PNJ": "CONSUMER",
    "SAB": "CONSUMER",
    "VNM": "CONSUMER",
    # Technology (Công nghệ)
    "FPT": "TECH",
    # Finance / Securities (Tài chính, chứng khoán)
    "BVH": "FINANCE",
    "SSI": "FINANCE",
    # Agri / Rubber (Nông nghiệp / Cao su)
    "GVR": "AGRI",
    # Airlines (Hàng không)
    "VJC": "AIRLINES",
    # Conglomerate / Diversified (Tập đoàn đa ngành)
    "MSN": "CONGLOMERATE",
}

_DEFAULT_SECTOR = "OTHER"


def get_sector(symbol: str) -> str:
    """Return sector string for a symbol. Falls back to 'OTHER' if unknown."""
    return _VN30_SECTOR_MAP.get(symbol.upper(), _DEFAULT_SECTOR)


def sector_count(symbols: list[str]) -> dict[str, int]:
    """Return {sector: count} for a list of open position symbols."""
    counts: dict[str, int] = {}
    for s in symbols:
        sec = get_sector(s)
        counts[sec] = counts.get(sec, 0) + 1
    return counts


def can_add_to_sector(
    symbol: str,
    open_symbols: list[str],
    max_per_sector: int = 2,
) -> bool:
    """Return True if adding `symbol` keeps sector count ≤ max_per_sector."""
    sec = get_sector(symbol)
    if sec == _DEFAULT_SECTOR:
        return True  # unknown sector → permissive
    current = sum(1 for s in open_symbols if get_sector(s) == sec)
    return current < max_per_sector
