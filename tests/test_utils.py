"""Tests for gems_cli.utils — pure Python utilities."""

from pathlib import Path

import pytest

from gems_cli.utils import (
    bar_to_pascal,
    celsius_to_kelvin,
    filter_near_zero,
    find_system_dat_lst,
    list_available_systems,
    resolve_data_dir,
    validate_bulk_composition,
)


class TestUnitConversions:
    def test_celsius_to_kelvin(self):
        assert celsius_to_kelvin(0) == 273.15
        assert celsius_to_kelvin(-273.15) == 0
        assert celsius_to_kelvin(100) == 373.15
        assert celsius_to_kelvin(25) == 298.15

    def test_bar_to_pascal(self):
        assert bar_to_pascal(1) == 1e5
        assert bar_to_pascal(0) == 0
        assert bar_to_pascal(100) == 1e7


class TestFilterNearZero:
    def test_basic_filtering(self):
        result = filter_near_zero({"a": 1.0, "b": 1e-16, "c": 0.001})
        assert result == {"a": 1.0, "c": 0.001}

    def test_empty_dict(self):
        assert filter_near_zero({}) == {}

    def test_all_near_zero(self):
        assert filter_near_zero({"a": 1e-16, "b": 1e-20}) == {}

    def test_negative_values_excluded(self):
        result = filter_near_zero({"a": -1e-16, "b": -1.0})
        assert result == {"b": -1.0}

    def test_custom_threshold(self):
        result = filter_near_zero({"a": 0.5, "b": 0.9}, threshold=1.0)
        assert result == {}


class TestResolveDataDir:
    def test_returns_path(self):
        result = resolve_data_dir()
        assert isinstance(result, Path)

    def test_path_ends_with_systems(self):
        result = resolve_data_dir()
        assert result.name == "systems"
        assert result.parent.name == "data"

    def test_path_exists(self):
        result = resolve_data_dir()
        assert result.exists()


class TestListAvailableSystems:
    def test_returns_sorted_list(self):
        systems = list_available_systems()
        assert isinstance(systems, list)
        assert systems == sorted(systems)

    def test_contains_known_systems(self):
        systems = list_available_systems()
        assert "calcite" in systems
        assert "cement_hydration" in systems


class TestFindSystemDatLst:
    def test_success(self):
        result = find_system_dat_lst("calcite")
        assert isinstance(result, Path)
        assert result.suffix == ".lst"
        assert result.exists()

    def test_system_not_found(self):
        with pytest.raises(FileNotFoundError, match="Available systems"):
            find_system_dat_lst("nonexistent_system_xyz")

    def test_no_lst_file(self, monkeypatch, tmp_path):
        # Create a system dir with no .lst files
        sys_dir = tmp_path / "empty_system" / "gemsfiles"
        sys_dir.mkdir(parents=True)
        (sys_dir / "data.json").write_text("{}")
        monkeypatch.setattr("gems_cli.utils.resolve_data_dir", lambda: tmp_path)
        with pytest.raises(FileNotFoundError, match="No .lst file found"):
            find_system_dat_lst("empty_system")


class TestValidateBulkComposition:
    def test_valid_composition(self):
        valid, warnings = validate_bulk_composition({"Ca": 0.01, "H": 111.0, "O": 55.5})
        assert valid is True
        assert warnings == []

    def test_zero_value_detected(self):
        valid, warnings = validate_bulk_composition({"Ca": 0.0, "H": 111.0})
        assert valid is False
        assert any("zero/near-zero" in w for w in warnings)
        assert "Ca" in warnings[0]

    def test_near_zero_value_detected(self):
        valid, warnings = validate_bulk_composition({"Ca": 1e-20, "H": 111.0})
        assert valid is False
        assert any("zero/near-zero" in w for w in warnings)

    def test_unknown_element_detected(self):
        valid, warnings = validate_bulk_composition(
            {"Ca": 0.01, "Xx": 1.0},
            system_elements=["Ca", "C", "H", "O"],
        )
        assert valid is False
        assert any("not in the system" in w for w in warnings)
        assert any("Xx" in w for w in warnings)

    def test_known_element_passes(self):
        valid, warnings = validate_bulk_composition(
            {"Ca": 0.01, "H": 111.0},
            system_elements=["Ca", "C", "H", "O"],
        )
        assert valid is True
        assert warnings == []

    def test_multiple_issues(self):
        valid, warnings = validate_bulk_composition(
            {"Ca": 0.0, "Xx": 1.0, "H": 111.0},
            system_elements=["Ca", "C", "H", "O"],
        )
        assert valid is False
        assert len(warnings) == 2

    def test_empty_composition(self):
        valid, warnings = validate_bulk_composition({})
        assert valid is True
        assert warnings == []
