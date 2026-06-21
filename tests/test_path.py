"""Tests for gems_cli.path — PathCalculator."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from tests.conftest import mock_find_system  # noqa: F401 — re-export for fixtures
from tests.conftest import MockChemicalEngineDicts


# =============================================================================
# MockChemicalEngine — mimics xgems.ChemicalEngine low-level API
# =============================================================================
class MockChemicalEngine:
    """Mimics xgems.ChemicalEngine for testing without conda.

    Key differences from MockChemicalEngineDicts:
    - pH(), pe() are methods (not properties)
    - equilibrate(T, P, b) takes explicit args
    - reequilibrate(warmstart) returns status code
    - setB(b), setPT(T, P) are explicit setters
    - Results are numpy arrays, not dicts
    """

    def __init__(self, lst_path: str = "mock.lst"):
        self._lst_path = lst_path
        # Internal state
        self._T = 298.15
        self._P = 1e5
        self._b = np.array([0.01, 0.01, 111.0, 55.5])  # Ca, C, H, O
        self._elements = ["Ca", "C", "H", "O"]
        self._phases = ["Calcite", "Aragonite", "aq_gen"]
        self._species = ["Ca+2", "HCO3-", "Calcite"]
        self._converged = True
        self._last_status = 6
        self._num_iters = 3
        self._warmstart = False
        # Results
        self._pH = 8.31
        self._pe = 4.0
        self._ionic_strength = 0.0042
        self._system_volume = 1.0001e-6
        self._system_mass = 1.001
        self._phase_amounts = np.array([0.0098, 1e-16, 0.012])
        self._phase_volumes = np.array([3.69e-6, 1e-20, 9.96e-7])
        self._phase_masses = np.array([0.00098, 1e-20, 0.00102])
        self._phase_sat_indices = np.array([0.0, -0.12, 0.0])
        self._species_molalities = np.array([0.0021, 0.0019, 0.0098])
        self._ln_gamma = np.array([-0.05, -0.04, 0.0])

    # --- Index lookups ---
    def indexElement(self, name: str) -> int:
        return self._elements.index(name)

    def indexPhase(self, name: str) -> int:
        return self._phases.index(name)

    def indexSpecies(self, name: str) -> int:
        return self._species.index(name)

    # --- Counts ---
    def numElements(self) -> int:
        return len(self._elements)

    def numPhases(self) -> int:
        return len(self._phases)

    def numSpecies(self) -> int:
        return len(self._species)

    # --- Name lookups ---
    def elementName(self, i: int) -> str:
        return self._elements[i]

    def phaseName(self, i: int) -> str:
        return self._phases[i]

    def speciesName(self, i: int) -> str:
        return self._species[i]

    # --- State access ---
    def elementAmounts(self) -> np.ndarray:
        return self._b.copy()

    def phaseAmounts(self) -> np.ndarray:
        return self._phase_amounts.copy()

    def speciesAmounts(self) -> np.ndarray:
        return np.array([0.0021, 0.0019, 0.0098])

    def phaseVolumes(self) -> np.ndarray:
        return self._phase_volumes.copy()

    def phaseMasses(self) -> np.ndarray:
        return self._phase_masses.copy()

    def phaseSatIndices(self) -> np.ndarray:
        return self._phase_sat_indices.copy()

    def speciesMolalities(self) -> np.ndarray:
        return self._species_molalities.copy()

    def lnActivityCoefficients(self) -> np.ndarray:
        return self._ln_gamma.copy()

    # --- Scalar results (methods, not properties) ---
    def pH(self) -> float:
        return self._pH

    def pe(self) -> float:
        return self._pe

    def ionicStrength(self) -> float:
        return self._ionic_strength

    def systemVolume(self) -> float:
        return self._system_volume

    def systemMass(self) -> float:
        return self._system_mass

    # --- State mutation ---
    def setPT(self, T: float, P: float):
        self._T = T
        self._P = P

    def setB(self, b):
        self._b = np.array(b)

    def setWarmStart(self):
        self._warmstart = True

    def setColdStart(self):
        self._warmstart = False

    def setSpeciesLowerLimit(self, name: str, amount: float):
        pass

    def setSpeciesUpperLimit(self, name: str, amount: float):
        pass

    # --- Equilibration ---
    def equilibrate(self, T: float, P: float, b):
        self._T = T
        self._P = P
        self._b = np.array(b)
        self._converged = True

    def reequilibrate(self, warmstart: bool = True) -> int:
        self._warmstart = warmstart
        return self._last_status

    def converged(self) -> bool:
        return self._converged

    def numIterations(self) -> int:
        return self._num_iters

    # --- DBR I/O ---
    def writeDbrToJsonString(self) -> str:
        return '{"mock": "dbr_state"}'

    def readDbrFromJsonString(self, json_str: str):
        pass


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def mock_check_xgems_lowlevel(monkeypatch):
    """Patch check_xgems_lowlevel to return MockChemicalEngine."""
    monkeypatch.setattr("gems_cli.path.check_xgems_lowlevel", lambda: MockChemicalEngine)
    return MockChemicalEngine


@pytest.fixture
def mock_find_system_path(monkeypatch, tmp_path):
    """Patch find_system_dat_lst to return a temp .lst file."""
    lst_file = tmp_path / "calcite-dat.lst"
    lst_file.write_text("mock lst content")
    monkeypatch.setattr("gems_cli.path.find_system_dat_lst", lambda name: lst_file)
    return lst_file


@pytest.fixture
def calc(mock_find_system_path, mock_check_xgems_lowlevel):
    """Create a PathCalculator with mocked engine."""
    from gems_cli.path import PathCalculator

    return PathCalculator(system_name="calcite")


# =============================================================================
# TestPathCalculatorInit
# =============================================================================
class TestPathCalculatorInit:
    def test_no_args_raises(self):
        from gems_cli.path import PathCalculator

        with pytest.raises(ValueError):
            PathCalculator()

    def test_bad_path_raises(self):
        from gems_cli.path import PathCalculator

        with pytest.raises(FileNotFoundError):
            PathCalculator(lst_path="/nonexistent/file.dat.lst")

    def test_by_system_name(self, calc):
        assert calc.system_name == "calcite"

    def test_by_lst_path(self, tmp_path):
        from gems_cli.path import PathCalculator

        lst_file = tmp_path / "mysystem-dat.lst"
        lst_file.write_text("mock")
        calc = PathCalculator(lst_path=str(lst_file))
        assert calc.system_name == "mysystem"


# =============================================================================
# TestBuildBVector
# =============================================================================
class TestBuildBVector:
    def _make_engine(self):
        return MockChemicalEngine()

    def test_partial_dict(self):
        from gems_cli.path import _build_b_vector

        eng = self._make_engine()
        b = _build_b_vector(eng, {"Ca": 1.17, "H": 222.0})
        # Ca=idx0 -> 1.17, C=idx1 -> 0.01 (default), H=idx2 -> 222.0, O=idx3 -> 55.5 (default)
        assert b[0] == pytest.approx(1.17)
        assert b[1] == pytest.approx(0.01)
        assert b[2] == pytest.approx(222.0)
        assert b[3] == pytest.approx(55.5)

    def test_full_dict(self):
        from gems_cli.path import _build_b_vector

        eng = self._make_engine()
        b = _build_b_vector(eng, {"Ca": 0.5, "C": 0.3, "H": 100.0, "O": 50.0})
        assert b == pytest.approx([0.5, 0.3, 100.0, 50.0])

    def test_empty_dict_returns_defaults(self):
        from gems_cli.path import _build_b_vector

        eng = self._make_engine()
        default = list(eng.elementAmounts())
        b = _build_b_vector(eng, {})
        assert b == pytest.approx(default)

    def test_unknown_element_ignored(self):
        from gems_cli.path import _build_b_vector

        eng = self._make_engine()
        b = _build_b_vector(eng, {"Ca": 0.5, "Xe": 999.0})
        assert b[0] == pytest.approx(0.5)
        assert len(b) == 4  # Xe not added


# =============================================================================
# TestPathCalculatorEquilibrate
# =============================================================================
class TestPathCalculatorEquilibrate:
    def test_success(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01, "C": 0.01, "H": 111.0, "O": 55.5})
        assert result["status"] == "success"
        assert "system" in result
        assert "phases" in result
        assert "path_info" in result
        assert result["path_info"]["converged"] is True

    def test_default_conditions(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        assert result["conditions"]["T_K"] == pytest.approx(298.15)
        assert result["conditions"]["P_Pa"] == pytest.approx(1e5)

    def test_celsius_override(self, calc):
        result = calc.equilibrate(
            bulk_composition={"Ca": 0.01}, T_celsius=50, P_bar=2.0,
        )
        assert result["conditions"]["T_K"] == pytest.approx(323.15)
        assert result["conditions"]["P_Pa"] == pytest.approx(2e5)

    def test_phases_filtered(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        phases = result["phases"]
        # Aragonite has 1e-16 moles — should be filtered
        assert "Aragonite" not in phases["names"]
        assert "Calcite" in phases["names"]


# =============================================================================
# TestPathCalculatorStep
# =============================================================================
class TestPathCalculatorStep:
    def test_warmstart_step(self, calc):
        # First call initializes engine
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        # Step with warm-start
        result = calc.step(bulk_composition={"Ca": 0.02}, warmstart=True)
        assert result["status"] == "success"
        assert result["path_info"]["warmstart_used"] is True
        assert result["path_info"]["reequilibrate_status"] == 6

    def test_coldstart_step(self, calc):
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        result = calc.step(bulk_composition={"Ca": 0.02}, warmstart=False)
        assert result["path_info"]["warmstart_used"] is False

    def test_convergence_fallback(self, calc, mock_check_xgems_lowlevel):
        """When warm-start returns bad status, should fallback to cold-start."""
        calc.equilibrate(bulk_composition={"Ca": 0.01})

        # Make reequilibrate return bad status on first call (warmstart),
        # then OK on second call (coldstart)
        engine = calc._engine
        call_count = [0]
        original_reeq = engine.reequilibrate

        def mock_reeq(warmstart):
            call_count[0] += 1
            if warmstart:
                return 7  # bad-SIA
            return 2  # OK-AIA

        engine.reequilibrate = mock_reeq

        result = calc.step(bulk_composition={"Ca": 0.05}, warmstart=True)
        assert call_count[0] == 2  # called twice: warm then cold
        assert result["path_info"]["warmstart_used"] is False
        assert result["path_info"]["reequilibrate_status"] == 2

    def test_no_bulk_change(self, calc):
        """Step without bulk_composition should still work."""
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        result = calc.step(warmstart=True)
        assert result["status"] == "success"

    def test_t_p_override(self, calc):
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        result = calc.step(T_celsius=75, P_bar=5.0)
        assert result["conditions"]["T_K"] == pytest.approx(348.15)
        assert result["conditions"]["P_Pa"] == pytest.approx(5e5)


# =============================================================================
# TestPathCalculatorRunPath
# =============================================================================
class TestPathCalculatorRunPath:
    def test_basic_sequence(self, calc):
        sequence = [
            {"Ca": 0.01, "H": 111.0, "O": 55.5},
            {"Ca": 0.02, "H": 111.0, "O": 55.5},
            {"Ca": 0.03, "H": 111.0, "O": 55.5},
        ]
        results = calc.run_path(sequence)
        assert len(results) == 3
        for r in results:
            assert r["status"] == "success"

    def test_empty_sequence(self, calc):
        results = calc.run_path([])
        assert results == []


# =============================================================================
# TestExtractResults
# =============================================================================
class TestExtractResults:
    def test_result_schema(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        expected_keys = {"status", "conditions", "system", "phases",
                         "saturation_indices", "aqueous_species", "diagnostics",
                         "activity_coefficients", "path_info"}
        assert expected_keys == set(result.keys())

    def test_system_values(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        sys_ = result["system"]
        assert sys_["pH"] == pytest.approx(8.31)
        assert sys_["pE"] == pytest.approx(4.0)
        assert sys_["ionic_strength"] == pytest.approx(0.0042)

    def test_volume_conversion(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        # Calcite volume: 3.69e-6 m3 -> 3.69 cm3
        phases = result["phases"]
        idx = phases["names"].index("Calcite")
        assert phases["volume_cm3"][idx] == pytest.approx(3.69, rel=1e-2)

    def test_mass_conversion(self, calc):
        result = calc.equilibrate(bulk_composition={"Ca": 0.01})
        phases = result["phases"]
        idx = phases["names"].index("Calcite")
        # 0.00098 kg -> 0.98 g
        assert phases["mass_g"][idx] == pytest.approx(0.98, rel=1e-2)


# =============================================================================
# TestDBRIO
# =============================================================================
class TestDBRIO:
    def test_export_state(self, calc):
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        state = calc.export_dbr_state()
        assert isinstance(state, str)
        assert "mock" in state

    def test_load_state(self, calc):
        calc.equilibrate(bulk_composition={"Ca": 0.01})
        calc.load_dbr_state('{"mock": "loaded"}')


# =============================================================================
# TestElementPhaseSpeciesNames
# =============================================================================
class TestElementPhaseSpeciesNames:
    def test_element_names(self, calc):
        assert calc.element_names == ["Ca", "C", "H", "O"]

    def test_phase_names(self, calc):
        assert calc.phase_names == ["Calcite", "Aragonite", "aq_gen"]

    def test_species_names(self, calc):
        assert calc.species_names == ["Ca+2", "HCO3-", "Calcite"]
