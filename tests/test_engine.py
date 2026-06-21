"""Tests for gems_cli.engine — GemsEngine + GemsExplorer."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gems_cli.engine import GemsEngine, GemsExplorer
from tests.conftest import MockChemicalEngineDicts, make_engine_with_data


# =============================================================================
# TestGemsEngineInit
# =============================================================================
class TestGemsEngineInit:
    def test_no_args_raises(self):
        with pytest.raises(ValueError):
            GemsEngine()

    def test_bad_path_raises(self):
        with pytest.raises(FileNotFoundError):
            GemsEngine(lst_path="/nonexistent/file.dat.lst")

    def test_by_system_name(self, mock_find_system, mock_check_xgems):
        engine = GemsEngine(system_name="calcite")
        assert engine.system_name == "calcite"

    def test_by_lst_path(self, tmp_path):
        lst_file = tmp_path / "mysystem-dat.lst"
        lst_file.write_text("mock")
        engine = GemsEngine(lst_path=str(lst_file))
        assert engine.system_name == "mysystem"


# =============================================================================
# TestCreateEngine — regression tests
# =============================================================================
class TestCreateEngine:
    def test_fresh_each_time(self, mock_find_system, mock_check_xgems):
        engine = GemsEngine(system_name="calcite")
        e1 = engine._create_engine()
        e2 = engine._create_engine()
        assert e1 is not e2

    def test_restores_cwd(self, mock_find_system, mock_check_xgems):
        engine = GemsEngine(system_name="calcite")
        original_cwd = os.getcwd()
        engine._create_engine()
        assert os.getcwd() == original_cwd


# =============================================================================
# TestGemsEngineEquilibrate
# =============================================================================
class TestGemsEngineEquilibrate:
    def _make_engine(self, mock_find_system, mock_check_xgems):
        return GemsEngine(system_name="calcite")

    def test_success(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        result = engine.equilibrate()
        assert result["status"] == "success"
        assert "conditions" in result
        assert "system" in result
        assert "phases" in result
        assert "saturation_indices" in result

    def test_celsius_override(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        engine._create_engine = lambda: mock_eng
        engine.equilibrate(T_celsius=25, P_bar=1)
        assert mock_eng.T == pytest.approx(298.15)
        assert mock_eng.P == pytest.approx(1e5)

    def test_kelvin_pascal_direct(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        engine._create_engine = lambda: mock_eng
        engine.equilibrate(T=373.15, P=1e6)
        assert mock_eng.T == 373.15
        assert mock_eng.P == 1e6

    def test_convergence_error(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        mock_eng.equilibrate = MagicMock(side_effect=RuntimeError("did not converge"))
        engine._create_engine = lambda: mock_eng
        result = engine.equilibrate()
        assert result["status"] == "error"
        assert result["error_type"] == "convergence"
        assert "did not converge" in result["message"]

    def test_suppress_phase_error(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        mock_eng.suppress_multiple_phases = MagicMock(side_effect=Exception("bad phase"))
        engine._create_engine = lambda: mock_eng
        result = engine.equilibrate(suppress_phases=["BadPhase"])
        assert result["status"] == "error"
        assert result["error_type"] == "suppress"

    def test_suppress_species_error(self, mock_find_system, mock_check_xgems):
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        mock_eng.suppress_multiple_species = MagicMock(side_effect=Exception("bad species"))
        engine._create_engine = lambda: mock_eng
        result = engine.equilibrate(suppress_species=["BadSpecies"])
        assert result["status"] == "error"
        assert result["error_type"] == "suppress"

    def test_zero_bulk_composition_regression(self, mock_find_system, mock_check_xgems):
        """Regression: set_bulk_composition IS called even with zero values.

        The engine itself does not filter zeros — this is the caller's
        documented bug pattern. This test documents current behavior.
        """
        engine = self._make_engine(mock_find_system, mock_check_xgems)
        mock_eng = MockChemicalEngineDicts()
        mock_eng.set_bulk_composition = MagicMock()
        engine._create_engine = lambda: mock_eng
        bulk = {"Ca": 0, "C": 0}
        engine.equilibrate(bulk_composition=bulk)
        mock_eng.set_bulk_composition.assert_called_once_with(bulk)


# =============================================================================
# TestExtractResults — most important test group
# =============================================================================
class TestExtractResults:
    def _extract(self, engine=None, T=298.15, P=1e5, **overrides):
        if engine is None:
            engine = make_engine_with_data(**overrides)
        # Create a minimal GemsEngine to call the instance method
        ge = GemsEngine.__new__(GemsEngine)
        ge._system_name = "test"
        return ge._extract_results(engine, T, P)

    def test_success_keys(self):
        result = self._extract()
        expected_keys = {"status", "conditions", "system", "phases", "saturation_indices"}
        assert expected_keys.issubset(result.keys())
        assert result["status"] == "success"

    def test_conditions(self):
        result = self._extract(T=373.15, P=1e6)
        assert result["conditions"] == {"T_K": 373.15, "P_Pa": 1e6}

    def test_system_scalars(self):
        result = self._extract()
        sys_ = result["system"]
        assert sys_["pH"] == pytest.approx(8.31)
        assert sys_["pE"] == pytest.approx(4.0)
        assert sys_["ionic_strength"] == pytest.approx(0.0042)
        assert sys_["volume_m3"] == pytest.approx(1.0001e-6)
        assert sys_["mass_kg"] == pytest.approx(1.001)

    def test_phases_moles_dict(self):
        result = self._extract()
        phases = result["phases"]
        # Aragonite (1e-16) should be filtered out
        assert "Aragonite" not in phases["names"]
        assert "Calcite" in phases["names"]
        assert "aq_gen" in phases["names"]

    def test_phases_moles_list(self):
        engine = make_engine_with_data()
        engine.phases_moles = [0.0098, 1e-16, 0.012]
        result = self._extract(engine=engine)
        phases = result["phases"]
        assert len(phases["names"]) == 2  # Aragonite filtered
        assert "Calcite" in phases["names"]

    def test_near_zero_filtered(self):
        engine = make_engine_with_data()
        engine.phases_moles = {"PhaseA": 1e-16, "PhaseB": 0.5}
        engine.phase_names = ["PhaseA", "PhaseB"]
        result = self._extract(engine=engine)
        assert result["phases"]["names"] == ["PhaseB"]
        assert result["phases"]["moles"] == [0.5]

    def test_volume_conversion(self):
        engine = make_engine_with_data()
        engine.phases_volume = {"Calcite": 3.69e-6}
        result = self._extract(engine=engine)
        vol = result["phases"]["volume_cm3"]
        # 3.69e-6 m³ * 1e6 = 3.69 cm³
        assert vol[0] == pytest.approx(3.69, rel=1e-3)

    def test_mass_conversion(self):
        engine = make_engine_with_data()
        engine.phases_mass = {"Calcite": 0.001}
        result = self._extract(engine=engine)
        mass = result["phases"]["mass_g"]
        # 0.001 kg * 1e3 = 1.0 g
        assert mass[0] == pytest.approx(1.0, rel=1e-3)

    def test_saturation_indices_dict(self):
        result = self._extract()
        si = result["saturation_indices"]
        assert isinstance(si, dict)
        assert "Calcite" in si

    def test_saturation_indices_list(self):
        engine = make_engine_with_data()
        engine.phase_sat_indices = [0.0, -0.12, 0.0]
        result = self._extract(engine=engine)
        si = result["saturation_indices"]
        assert isinstance(si, dict)
        assert si["Calcite"] == 0.0
        assert si["Aragonite"] == -0.12

    def test_aqueous_optional_present(self):
        result = self._extract()
        assert "aqueous_species" in result
        assert "molality" in result["aqueous_species"]
        assert "Ca+2" in result["aqueous_species"]["molality"]

    def test_aqueous_optional_absent(self, monkeypatch):
        engine = make_engine_with_data()
        monkeypatch.delattr(engine, "aq_species_molality")
        # Also remove molarity since it's checked after molality
        monkeypatch.delattr(engine, "aq_species_molarity")
        result = self._extract(engine=engine)
        assert "aqueous_species" not in result

    def test_species_moles_dict(self):
        result = self._extract()
        assert "species" in result
        assert "moles" in result["species"]

    def test_species_moles_list(self):
        engine = make_engine_with_data()
        engine.species_moles = [0.0021, 0.0019, 0.0098]
        result = self._extract(engine=engine)
        assert "species" in result
        assert len(result["species"]["moles"]) == 3

    def test_solids_optional_present(self):
        result = self._extract()
        assert "solids" in result
        assert "mass_frac" in result["solids"]

    def test_solids_absent_when_empty(self):
        engine = make_engine_with_data()
        engine.solids_mass_frac = {}
        engine.solids_volume_frac = {}
        result = self._extract(engine=engine)
        assert "solids" not in result

    def test_all_optional_absent(self, monkeypatch):
        engine = make_engine_with_data()
        monkeypatch.delattr(engine, "aq_species_molality")
        monkeypatch.delattr(engine, "aq_species_molarity")
        monkeypatch.delattr(engine, "phases_volume")
        monkeypatch.delattr(engine, "phases_mass")
        monkeypatch.delattr(engine, "phases_volume_frac")
        monkeypatch.delattr(engine, "solids_mass_frac")
        monkeypatch.delattr(engine, "solids_volume_frac")
        monkeypatch.delattr(engine, "species_moles")
        monkeypatch.delattr(engine, "element_molar_masses")
        monkeypatch.delattr(engine, "phases_molar_volume")
        monkeypatch.delattr(engine, "aq_elements_amounts")
        monkeypatch.delattr(engine, "solid_elements_amounts")
        result = self._extract(engine=engine)
        expected = {"status", "conditions", "system", "phases", "saturation_indices", "diagnostics"}
        assert set(result.keys()) == expected

    def test_diagnostics_field(self):
        result = self._extract()
        diag = result.get("diagnostics", {})
        assert diag["n_elements"] == 4
        assert diag["n_phases"] == 3  # Calcite, Aragonite(filtered), aq_gen
        assert isinstance(diag["n_species"], int)

    def test_composition_field(self):
        result = self._extract()
        comp = result.get("composition", {})
        assert "element_molar_masses" in comp
        assert "phase_molar_volume" in comp
        # Verify values are correctly aligned (Ca should map to 40.08, not 12.01)
        assert comp["element_molar_masses"]["Ca"] == pytest.approx(40.08)
        assert comp["element_molar_masses"]["C"] == pytest.approx(12.01)

    def test_element_balance_field(self):
        result = self._extract()
        bal = result.get("element_balance", {})
        assert "aqueous" in bal
        assert "solid" in bal
        # Verify values are correct (Ca aqueous = 0.0021, not some other element's value)
        assert bal["aqueous"]["Ca"] == pytest.approx(0.0021)
        assert bal["solid"]["Ca"] == pytest.approx(0.0077)

    def test_composition_absent_when_attributes_missing(self, monkeypatch):
        engine = make_engine_with_data()
        monkeypatch.delattr(engine, "element_molar_masses")
        monkeypatch.delattr(engine, "phases_molar_volume")
        result = self._extract(engine=engine)
        assert "composition" not in result

    def test_element_balance_absent_when_attributes_missing(self, monkeypatch):
        engine = make_engine_with_data()
        monkeypatch.delattr(engine, "aq_elements_amounts")
        monkeypatch.delattr(engine, "solid_elements_amounts")
        result = self._extract(engine=engine)
        assert "element_balance" not in result


# =============================================================================
# TestGemsExplorer
# =============================================================================
class TestGemsExplorer:
    def test_list_systems_delegates(self, mock_list_systems):
        result = GemsExplorer.list_systems()
        assert result == ["calcite", "cement_hydration", "ferrite_carbonation"]

    def test_system_info_success(self, mock_find_system, mock_check_xgems):
        info = GemsExplorer.system_info("calcite")
        assert info["system"] == "calcite"
        assert "elements" in info
        assert "phases" in info
        assert "n_elements" in info
        assert "n_phases" in info

    def test_system_info_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.engine.find_system_dat_lst",
            lambda name: (_ for _ in ()).throw(FileNotFoundError("System 'bad' not found")),
        )
        with pytest.raises(FileNotFoundError, match="bad"):
            GemsExplorer.system_info("bad")
