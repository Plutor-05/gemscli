"""Shared utilities: unit conversion, path resolution, result formatting."""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def celsius_to_kelvin(t_c: float) -> float:
    return t_c + 273.15


def bar_to_pascal(p_bar: float) -> float:
    return p_bar * 1e5


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_data_dir() -> Path:
    """Return the data/ directory containing pre-exported GEMS3K system files."""
    return Path(__file__).resolve().parent.parent / "data" / "systems"


def list_available_systems() -> list[str]:
    """Return names of pre-packaged GEMS3K systems in data/systems/."""
    data_dir = resolve_data_dir()
    if not data_dir.is_dir():
        return []
    return sorted(d.name for d in data_dir.iterdir() if d.is_dir())


def find_system_dat_lst(system_name: str) -> Path:
    """Find the *-dat.lst file for a pre-packaged system.

    Supports both .json (flag -j) and .dat (flag -t) variants.
    """
    system_dir = resolve_data_dir() / system_name / "gemsfiles"
    if not system_dir.is_dir():
        raise FileNotFoundError(
            f"System '{system_name}' not found at {system_dir}.\n"
            f"Available systems: {list_available_systems()}"
        )

    # Look for *-dat.lst
    lst_files = list(system_dir.glob("*-dat.lst"))
    if lst_files:
        return lst_files[0]

    # Fallback: any .lst file
    lst_files = list(system_dir.glob("*.lst"))
    if lst_files:
        return lst_files[0]

    raise FileNotFoundError(f"No .lst file found in {system_dir}")


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def filter_near_zero(d: dict[str, float], threshold: float = 1e-15) -> dict[str, float]:
    """Remove entries whose absolute value is below threshold."""
    return {k: v for k, v in d.items() if abs(v) >= threshold}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_NEAR_ZERO_THRESHOLD = 1e-15


def validate_bulk_composition(
    bulk: dict[str, float],
    system_elements: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate a bulk_composition dict before passing to xgems.

    Checks for zero/near-zero values and unknown elements.
    """
    warnings: list[str] = []

    for elem, value in bulk.items():
        if abs(value) < _NEAR_ZERO_THRESHOLD:
            warnings.append(
                f"Element '{elem}' has zero/near-zero value ({value}). "
                "Remove it from bulk_composition — xgems ignores composition "
                "updates when zero-valued elements are included."
            )

    if system_elements is not None:
        system_set = set(system_elements)
        for elem in bulk:
            if elem not in system_set:
                warnings.append(
                    f"Element '{elem}' is not in the system. "
                    f"Available elements: {sorted(system_set)}"
                )

    is_valid = not any(
        "zero/near-zero" in w or "not in the system" in w
        for w in warnings
    )
    return is_valid, warnings
