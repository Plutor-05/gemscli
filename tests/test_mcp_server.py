"""Tests for gems_cli.mcp_server — MCP tool functions.

Skipped entirely if the `mcp` package is not installed.
"""

import pytest

mcp = pytest.importorskip("mcp", reason="mcp package not installed")

from gems_cli.mcp_server import (
    _error_response,
    gems_batch_tp_scan,
    gems_equilibrate,
    gems_list_systems,
    gems_sweep,
    gems_diagnose,
    gems_analyze_species,
    gems_interpret,
    gems_system_info,
    gems_validate,
)
from tests.conftest import MockChemicalEngineDicts


# =============================================================================
# TestErrorResponse
# =============================================================================
class TestErrorResponse:
    def test_basic(self):
        result = _error_response("something went wrong")
        assert result == {"status": "error", "message": "something went wrong"}

    def test_with_details(self):
        result = _error_response("fail", {"code": 42})
        assert result["details"] == {"code": 42}


# =============================================================================
# TestGemsListSystems
# =============================================================================
class TestGemsListSystems:
    def test_returns_systems(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.list_systems",
            staticmethod(lambda: ["calcite", "iron_redox"]),
        )
        result = gems_list_systems()
        assert result["systems"] == ["calcite", "iron_redox"]
        assert result["count"] == 2


# =============================================================================
# TestGemsEquilibrate
# =============================================================================
class TestGemsEquilibrate:
    def test_success(self, monkeypatch):
        mock_eng = MockChemicalEngineDicts()
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsEngine",
            lambda system_name=None: mock_eng,
        )
        result = gems_equilibrate(system="calcite")
        assert result["status"] == "success"

    def test_file_not_found(self, monkeypatch):
        def raise_not_found(system_name=None):
            raise FileNotFoundError("System 'bad' not found")

        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", raise_not_found)
        result = gems_equilibrate(system="bad")
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_generic_error(self, monkeypatch):
        def raise_runtime(system_name=None):
            raise RuntimeError("solver failed")

        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", raise_runtime)
        result = gems_equilibrate(system="calcite")
        assert result["status"] == "error"
        assert "solver failed" in result["message"]


# =============================================================================
# TestGemsBatchTpScan
# =============================================================================
class TestGemsBatchTpScan:
    def test_batch(self, monkeypatch):
        def mock_init(system_name=None):
            eng = MockChemicalEngineDicts()
            return eng

        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", mock_init)
        result = gems_batch_tp_scan(
            system="calcite",
            T_range_celsius=[25.0, 50.0, 75.0],
            P_bar=1.0,
        )
        assert result["n_points"] == 3
        assert len(result["results"]) == 3
        for i, r in enumerate(result["results"]):
            assert r["T_celsius_input"] == [25.0, 50.0, 75.0][i]
            assert r["status"] == "success"


# =============================================================================
# TestGemsSystemInfo
# =============================================================================
class TestGemsSystemInfo:
    def test_success(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca"], "n_elements": 1}),
        )
        result = gems_system_info(system="calcite")
        assert result["system"] == "calcite"

    def test_not_found(self, monkeypatch):
        def raise_not_found(s):
            raise FileNotFoundError("System 'bad' not found")

        monkeypatch.setattr("gems_cli.mcp_server.GemsExplorer.system_info", raise_not_found)
        result = gems_system_info(system="bad")
        assert result["status"] == "error"


# =============================================================================
# TestGemsSweep
# =============================================================================
class TestGemsSweep:
    def test_temperature_sweep(self, monkeypatch):
        def mock_init(system_name=None):
            return MockChemicalEngineDicts()
        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", mock_init)
        result = gems_sweep(
            system="calcite",
            variable="T_celsius",
            var_range=[25.0, 50.0, 75.0],
        )
        assert result["n_points"] == 3
        assert result["variable"] == "T_celsius"
        assert len(result["results"]) == 3
        assert "transitions" in result

    def test_element_sweep(self, monkeypatch):
        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", lambda system_name=None: MockChemicalEngineDicts())
        result = gems_sweep(
            system="calcite",
            variable="C",
            var_range=[0.0, 0.01, 0.02],
            bulk_composition={"Ca": 0.01, "H": 111, "O": 55.5},
        )
        assert result["variable"] == "C"
        assert result["n_points"] == 3
        # Each result should have a var_value matching the sweep range
        for i, r in enumerate(result["results"]):
            assert r.get("var_value") == [0.0, 0.01, 0.02][i]

    def test_transitions_detected(self, monkeypatch):
        """Test that phase appearance/disappearance is detected."""
        call_count = 0

        def mock_init(system_name=None):
            nonlocal call_count
            eng = MockChemicalEngineDicts()
            call_count += 1
            # Simulate: Calcite disappears at point 2
            if call_count >= 3:
                eng.phases_moles = {"Aragonite": 0.01, "aq_gen": 0.5}
                eng.phase_names = ["Aragonite", "aq_gen"]
            return eng
        monkeypatch.setattr("gems_cli.mcp_server.GemsEngine", mock_init)
        result = gems_sweep(
            system="calcite",
            variable="C",
            var_range=[0.0, 0.01, 0.02, 0.03],
        )
        transitions = result["transitions"]
        calcite_transitions = [t for t in transitions if t["phase"] == "Calcite"]
        assert len(calcite_transitions) >= 1
        assert calcite_transitions[0]["event"] == "disappears"


# =============================================================================
# TestGemsDiagnose
# =============================================================================
class TestGemsDiagnose:
    def test_empty_results(self):
        result = gems_diagnose({"results": []})
        assert "error" in result

    def test_basic_diagnostics(self):
        sweep_results = {
            "variable": "C",
            "results": [
                {"status": "success", "system": {"pH": 12.0}, "phases": {"names": ["A"], "moles": [0.5]}, "saturation_indices": {"A": 0.5}},
                {"status": "success", "system": {"pH": 11.8}, "phases": {"names": ["A"], "moles": [0.4]}, "saturation_indices": {"A": 0.3}},
                {"status": "error", "message": "convergence failed"},
            ],
        }
        result = gems_diagnose(sweep_results)
        assert result["quality"]["total_points"] == 3
        assert result["quality"]["success_count"] == 2
        assert result["quality"]["error_count"] == 1
        assert 2 in result["quality"]["convergence_issues"]

    def test_pH_jump_detection(self):
        sweep_results = {
            "results": [
                {"status": "success", "system": {"pH": 7.0}, "phases": {"names": [], "moles": []}, "saturation_indices": {}},
                {"status": "success", "system": {"pH": 10.5}, "phases": {"names": [], "moles": []}, "saturation_indices": {}},
            ],
        }
        result = gems_diagnose(sweep_results)
        assert len(result["quality"]["pH_jumps"]) == 1
        assert result["quality"]["pH_jumps"][0]["delta_pH"] == pytest.approx(3.5)

    def test_oscillation_detection(self):
        sweep_results = {
            "results": [
                {"status": "success", "system": {"pH": 12.0}, "phases": {"names": ["P"], "moles": [0.001]}, "saturation_indices": {}},
                {"status": "success", "system": {"pH": 12.0}, "phases": {"names": ["P"], "moles": [0.8]}, "saturation_indices": {}},
                {"status": "success", "system": {"pH": 12.0}, "phases": {"names": ["P"], "moles": [0.001]}, "saturation_indices": {}},
            ],
        }
        result = gems_diagnose(sweep_results)
        assert 1 in result["quality"]["oscillation_suspects"]


# =============================================================================
# TestGemsAnalyzeSpecies
# =============================================================================
class TestGemsAnalyzeSpecies:
    def test_empty_results(self):
        result = gems_analyze_species({"results": []})
        assert "error" in result

    def test_basic_analysis(self):
        sweep_results = {
            "results": [
                {"status": "success", "aqueous_species": {"molality": {"Ca+2": 0.001, "OH-": 0.002, "Al+3": 0.0005}}},
                {"status": "success", "aqueous_species": {"molality": {"Ca+2": 0.003, "OH-": 0.001, "Al+3": 0.001}}},
            ],
        }
        result = gems_analyze_species(sweep_results, elements=["Ca"], top_n=5)
        assert len(result["species"]) == 1
        assert result["species"][0]["species"] == "Ca+2"
        assert result["species"][0]["max_molality"] == pytest.approx(0.003)

    def test_element_filter(self):
        sweep_results = {
            "results": [
                {"status": "success", "aqueous_species": {"molality": {"Ca+2": 0.001, "Al+3": 0.0005, "Fe+3": 0.0002}}},
            ],
        }
        result = gems_analyze_species(sweep_results, elements=["Al"])
        species_names = [s["species"] for s in result["species"]]
        assert "Al+3" in species_names
        assert "Ca+2" not in species_names


# =============================================================================
# TestGemsInterpret
# =============================================================================
class TestGemsInterpret:
    def test_failed_result(self):
        result = gems_interpret({"status": "error", "message": "convergence failed"})
        assert "failed" in result["summary"].lower()
        assert len(result["key_findings"]) == 0

    def test_successful_result(self):
        result = gems_interpret({
            "status": "success",
            "system": {"pH": 8.3, "ionic_strength": 0.005},
            "phases": {"names": ["Calcite", "Aragonite"], "moles": [0.01, 0.001]},
            "saturation_indices": {"Calcite": 0.0, "Aragonite": -0.12},
            "aqueous_species": {"molality": {"Ca+2": 0.002, "OH-": 0.001}},
        })
        assert len(result["key_findings"]) > 0
        assert "alkaline" in result["summary"].lower() or "pH" in result["summary"]
        assert isinstance(result["suggestions"], list)

    def test_high_pH_warning(self):
        result = gems_interpret({
            "status": "success",
            "system": {"pH": 13.5, "ionic_strength": 0.1},
            "phases": {"names": [], "moles": []},
            "saturation_indices": {},
        })
        assert len(result["warnings"]) > 0
        assert any("pH" in w for w in result["warnings"])


# =============================================================================
# TestGemsValidate
# =============================================================================
class TestGemsValidate:
    def test_valid_input(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca", "C", "H", "O"]}),
        )
        result = gems_validate(
            system="calcite",
            bulk_composition={"Ca": 0.01, "H": 111.0, "O": 55.5},
        )
        assert result["valid"] is True
        assert result["warnings"] == []
        assert result["system_elements"] == ["Ca", "C", "H", "O"]

    def test_zero_value_warning(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca", "C", "H", "O"]}),
        )
        result = gems_validate(
            system="calcite",
            bulk_composition={"Ca": 0.0, "H": 111.0, "O": 55.5},
        )
        assert result["valid"] is False
        assert any("zero/near-zero" in w for w in result["warnings"])

    def test_unknown_element_warning(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca", "C", "H", "O"]}),
        )
        result = gems_validate(
            system="calcite",
            bulk_composition={"Ca": 0.01, "Fe": 1.0, "H": 111.0},
        )
        assert result["valid"] is False
        assert any("not in the system" in w for w in result["warnings"])

    def test_temperature_below_zero(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca"]}),
        )
        result = gems_validate(system="calcite", T_celsius=-300.0)
        assert result["valid"] is False
        assert any("absolute zero" in w for w in result["warnings"])

    def test_negative_pressure(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca"]}),
        )
        result = gems_validate(system="calcite", P_bar=-1.0)
        assert result["valid"] is False
        assert any("positive" in w for w in result["warnings"])

    def test_empty_bulk_composition(self, monkeypatch):
        monkeypatch.setattr(
            "gems_cli.mcp_server.GemsExplorer.system_info",
            staticmethod(lambda s: {"system": s, "elements": ["Ca", "C", "H", "O"]}),
        )
        result = gems_validate(system="calcite", bulk_composition={})
        assert result["valid"] is True
        assert result["warnings"] == []

    def test_system_not_found(self, monkeypatch):
        def raise_not_found(s):
            raise FileNotFoundError("System 'bad' not found")
        monkeypatch.setattr("gems_cli.mcp_server.GemsExplorer.system_info", raise_not_found)
        result = gems_validate(system="bad")
        assert result["status"] == "error"
        assert "not found" in result["message"]
