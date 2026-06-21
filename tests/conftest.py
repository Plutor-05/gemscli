"""Shared fixtures and mock xgems engine for testing without conda."""

from __future__ import annotations

import types
from pathlib import Path

import pytest


class MockChemicalEngineDicts:
    """Mimics xgems.ChemicalEngineDicts for testing without conda."""

    def __init__(self, lst_path: str = "mock.lst"):
        self._lst_path = lst_path
        # Settable
        self.T = 298.15
        self.P = 1e5
        # Scalar results
        self.pH = 8.3
        self.pE = 4.0
        self.ionic_strength = 0.005
        self.system_volume = 1.0001e-6
        self.system_mass = 1.001
        self.nelements = 5
        self.nphases = 8
        self.nspecies = 12
        # List attributes
        self.element_names = ["Ca", "C", "H", "O", "Cl"]
        self.phase_names = ["Calcite", "Aragonite", "Portlandite", "aq_gen"]
        self.species_names = ["Ca+2", "CO3-2", "H+", "OH-", "HCO3-"]
        # Data attributes (dict form)
        self.phases_moles = {"Calcite": 0.01, "Aragonite": 0.001, "Portlandite": 0.005, "aq_gen": 0.5}
        self.phase_sat_indices = {"Calcite": 0.0, "Aragonite": -0.1, "Portlandite": 0.5, "aq_gen": 0.0}
        self.aq_species_molality = {"Ca+2": 0.001, "OH-": 0.002, "HCO3-": 0.0005}
        self.aq_species_molarity = {"Ca+2": 0.001, "OH-": 0.002, "HCO3-": 0.0005}
        self.phases_volume = {"Calcite": 3.69e-6, "Aragonite": 3.41e-7, "Portlandite": 1.655e-6, "aq_gen": 5e-7}
        self.phases_mass = {"Calcite": 0.001, "Aragonite": 0.0001, "Portlandite": 0.0005, "aq_gen": 0.0005}
        self.phases_volume_frac = {"Calcite": 0.369, "Aragonite": 0.0341, "Portlandite": 0.1655, "aq_gen": 0.05}
        self.solids_mass_frac = {"Calcite": 0.5, "Aragonite": 0.05, "Portlandite": 0.25, "aq_gen": 0.0}
        self.solids_volume_frac = {"Calcite": 0.369, "Aragonite": 0.0341, "Portlandite": 0.1655, "aq_gen": 0.0}
        self.species_moles = {"Ca+2": 0.001, "OH-": 0.002, "HCO3-": 0.0005}
        # New attributes for _extract_results extensions
        self.element_molar_masses = [40.08, 12.01, 1.008, 16.00, 35.45]
        self.phases_molar_volume = {"Calcite": 3.69e-5, "Aragonite": 3.41e-5, "Portlandite": 3.31e-5, "aq_gen": 1.0e-5}
        self.aq_elements_amounts = {"Ca": 0.001, "C": 0.0005, "H": 55.5, "O": 27.75, "Cl": 0.001}
        self.solid_elements_amounts = {"Ca": 0.009, "C": 0.0095, "H": 0.0, "O": 0.028, "Cl": 0.0}

    def set_bulk_composition(self, bulk: dict) -> None:
        self._bulk = bulk

    def equilibrate(self, **kwargs):
        # Return a result structure matching what _extract_results produces
        return {
            "status": "success",
            "system": {"pH": self.pH, "pE": self.pE, "ionic_strength": self.ionic_strength},
            "phases": {
                "names": list(self.phases_moles.keys()),
                "moles": list(self.phases_moles.values()),
            },
            "saturation_indices": dict(self.phase_sat_indices),
        }

    def suppress_multiple_phases(self, phases: list) -> None:
        pass

    def suppress_multiple_species(self, species: list) -> None:
        pass


def make_engine_with_data(**overrides):
    """Create MockChemicalEngineDicts with realistic calcite system data.

    Individual attributes can be overridden via keyword arguments.
    """
    engine = MockChemicalEngineDicts()
    engine.phase_names = ["Calcite", "Aragonite", "aq_gen"]
    engine.phases_moles = {"Calcite": 0.0098, "Aragonite": 1e-16, "aq_gen": 0.012}
    engine.phase_sat_indices = {"Calcite": 0.0, "Aragonite": -0.12, "aq_gen": 0.0}
    engine.phases_volume = {"Calcite": 3.69e-6, "Aragonite": 1e-20, "aq_gen": 9.96e-7}
    engine.phases_mass = {"Calcite": 0.00098, "Aragonite": 1e-20, "aq_gen": 0.00102}
    engine.phases_volume_frac = {"Calcite": 0.786, "Aragonite": 0.0, "aq_gen": 0.214}
    engine.solids_mass_frac = {"Calcite": 0.491, "Aragonite": 0.0, "aq_gen": 0.0}
    engine.solids_volume_frac = {"Calcite": 0.786, "Aragonite": 0.0, "aq_gen": 0.0}
    engine.aq_species_molality = {"Ca+2": 0.0021, "HCO3-": 0.0019}
    engine.aq_species_molarity = {"Ca+2": 0.0021, "HCO3-": 0.0019}
    engine.species_moles = {"Ca+2": 0.0021, "HCO3-": 0.0019, "Calcite": 0.0098}
    engine.species_names = ["Ca+2", "HCO3-", "Calcite"]
    engine.element_names = ["Ca", "C", "H", "O"]
    engine.nelements = 4
    engine.nphases = 3  # Calcite, Aragonite(filtered out but counted), aq_gen
    engine.nspecies = 3
    engine.element_molar_masses = [40.08, 12.01, 1.008, 16.00]
    engine.phases_molar_volume = {"Calcite": 3.69e-5, "Aragonite": 3.41e-5, "aq_gen": 1.0e-5}
    engine.aq_elements_amounts = {"Ca": 0.0021, "C": 0.0019, "H": 55.5, "O": 27.75}
    engine.solid_elements_amounts = {"Ca": 0.0077, "C": 0.0079, "H": 0.0, "O": 0.0294}
    engine.pH = 8.31
    engine.pE = 4.0
    engine.ionic_strength = 0.0042
    engine.system_volume = 1.0001e-6
    engine.system_mass = 1.001
    for k, v in overrides.items():
        setattr(engine, k, v)
    return engine


@pytest.fixture
def mock_check_xgems(monkeypatch):
    """Patch gems_cli.engine.check_xgems to return MockChemicalEngineDicts."""
    monkeypatch.setattr("gems_cli.engine.check_xgems", lambda: MockChemicalEngineDicts)
    return MockChemicalEngineDicts


@pytest.fixture
def mock_find_system(monkeypatch, tmp_path):
    """Patch find_system_dat_lst to return a temp .lst file."""
    lst_file = tmp_path / "calcite-dat.lst"
    lst_file.write_text("mock lst content")
    monkeypatch.setattr("gems_cli.engine.find_system_dat_lst", lambda name: lst_file)
    return lst_file


@pytest.fixture
def mock_list_systems(monkeypatch):
    """Patch list_available_systems to return known systems."""
    systems = ["calcite", "cement_hydration", "ferrite_carbonation"]
    monkeypatch.setattr("gems_cli.engine.list_available_systems", lambda: systems)
    return systems
