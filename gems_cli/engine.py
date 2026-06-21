"""Core engine wrapper around xGEMS ChemicalEngineDicts.

Provides GemsEngine: a high-level interface that handles system loading,
equilibrium calculation, and structured result extraction.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from gems_cli import check_xgems
from gems_cli.utils import (
    celsius_to_kelvin,
    bar_to_pascal,
    filter_near_zero,
    find_system_dat_lst,
    list_available_systems,
    validate_bulk_composition,
)

# Lock for os.chdir() to prevent race conditions in threaded MCP server
_cwd_lock = threading.Lock()


class GemsEngine:
    """High-level wrapper around xGEMS ChemicalEngineDicts.

    Usage::

        engine = GemsEngine("calcite")
        results = engine.equilibrate(T=298.15, P=1e5, bulk_composition={"Ca": 0.01, ...})
    """

    def __init__(self, system_name: str | None = None, lst_path: str | None = None):
        """Initialize engine from a pre-packaged system name or explicit .lst path.

        Args:
            system_name: Name of a system in data/systems/ (e.g. "calcite").
            lst_path: Direct path to a GEMS3K *-dat.lst file.
        """
        if system_name:
            self._lst_path = find_system_dat_lst(system_name)
            self._system_name = system_name
            # xgems resolves paths relative to CWD; change to the gemsfiles dir
            self._work_dir = self._lst_path.parent
        elif lst_path:
            self._lst_path = Path(lst_path)
            self._system_name = self._lst_path.stem.replace("-dat", "")
            self._work_dir = self._lst_path.parent
        else:
            raise ValueError("Provide either system_name or lst_path.")

        if not self._lst_path.exists():
            raise FileNotFoundError(f"lst file not found: {self._lst_path}")

        self._info_engine = None  # cached for metadata properties only

    def _create_engine(self):
        """Create a fresh ChemicalEngineDicts instance.

        CWD is changed to work_dir and NOT restored here.
        Caller must restore CWD after using the engine.
        """
        ChemicalEngineDicts = check_xgems()
        old_cwd = os.getcwd()
        os.chdir(str(self._work_dir))
        try:
            engine = ChemicalEngineDicts(str(self._lst_path))
        except Exception:
            os.chdir(old_cwd)
            raise
        # NOTE: CWD is now in work_dir; caller must restore it
        return engine, old_cwd

    def _get_info_engine(self):
        """Lazy-load engine for metadata properties only (element_names, etc.)."""
        if self._info_engine is None:
            engine, old_cwd = self._create_engine()
            os.chdir(old_cwd)
            self._info_engine = engine
        return self._info_engine

    @property
    def system_name(self) -> str:
        return self._system_name

    @property
    def element_names(self) -> list[str]:
        return self._get_info_engine().element_names

    @property
    def phase_names(self) -> list[str]:
        return self._get_info_engine().phase_names

    @property
    def species_names(self) -> list[str]:
        return self._get_info_engine().species_names

    def equilibrate(
        self,
        T: float = 298.15,
        P: float = 1e5,
        bulk_composition: dict[str, float] | None = None,
        suppress_species: list[str] | None = None,
        suppress_phases: list[str] | None = None,
        T_celsius: float | None = None,
        P_bar: float | None = None,
    ) -> dict[str, Any]:
        """Run equilibrium calculation and return structured results.

        Args:
            T: Temperature in Kelvin (default 298.15).
            P: Pressure in Pascal (default 1e5).
            bulk_composition: {element_symbol: moles} dict.
            suppress_species: Species names to suppress.
            suppress_phases: Phase names to suppress.
            T_celsius: Alternative temperature in Celsius (overrides T).
            P_bar: Alternative pressure in bar (overrides P).

        Returns:
            Structured dict with keys: status, conditions, system, phases, etc.
        """
        if T_celsius is not None:
            T = celsius_to_kelvin(T_celsius)
        if P_bar is not None:
            P = bar_to_pascal(P_bar)

        # _create_engine changes CWD to work_dir and returns (engine, old_cwd)
        # CWD must stay in work_dir through suppress/bulk/equilibrate calls
        # because xgems resolves internal paths relative to CWD
        with _cwd_lock:
            engine, old_cwd = self._create_engine()
            try:
                engine.T = T
                engine.P = P

                validation_warnings: list[str] = []
                if bulk_composition:
                    _, warnings = validate_bulk_composition(
                        bulk_composition, system_elements=engine.element_names,
                    )
                    validation_warnings.extend(warnings)
                    engine.set_bulk_composition(bulk_composition)

                if suppress_phases:
                    try:
                        engine.suppress_multiple_phases(suppress_phases)
                    except Exception as e:
                        os.chdir(old_cwd)
                        return {
                            "status": "error",
                            "error_type": "suppress",
                            "message": str(e),
                            "conditions": {"T_K": T, "P_Pa": P},
                        }

                if suppress_species:
                    try:
                        engine.suppress_multiple_species(suppress_species)
                    except Exception as e:
                        os.chdir(old_cwd)
                        return {
                            "status": "error",
                            "error_type": "suppress",
                            "message": str(e),
                            "conditions": {"T_K": T, "P_Pa": P},
                        }

                try:
                    engine.equilibrate()
                except RuntimeError as e:
                    os.chdir(old_cwd)
                    return {
                        "status": "error",
                        "error_type": "convergence",
                        "message": str(e),
                        "conditions": {"T_K": T, "P_Pa": P},
                    }

                result = self._extract_results(engine, T, P)
                if validation_warnings:
                    result["validation_warnings"] = validation_warnings
                return result
            finally:
                os.chdir(old_cwd)

    def _extract_results(self, engine, T: float, P: float) -> dict[str, Any]:
        """Extract all available results into a structured dictionary."""
        phase_names = engine.phase_names

        # Build phase results, filtering near-zero phases
        phases_moles_raw = engine.phases_moles
        if isinstance(phases_moles_raw, dict):
            phases_moles = phases_moles_raw
        else:
            phases_moles = dict(zip(phase_names, phases_moles_raw))

        active_phases = filter_near_zero(phases_moles)

        # Saturation indices
        sat_raw = engine.phase_sat_indices
        if isinstance(sat_raw, dict):
            sat_indices = sat_raw
        else:
            sat_indices = dict(zip(phase_names, sat_raw))

        # Aqueous species molality
        aq_molality = {}
        try:
            aq_raw = engine.aq_species_molality
            if isinstance(aq_raw, dict):
                aq_molality = filter_near_zero(aq_raw)
            else:
                aq_molality = filter_near_zero(dict(zip(engine.species_names, aq_raw)))
        except (AttributeError, Exception):
            pass

        # Phase volumes (m3 -> cm3)
        phases_vol = {}
        try:
            vol_raw = engine.phases_volume
            if isinstance(vol_raw, dict):
                phases_vol = {k: v * 1e6 for k, v in filter_near_zero(vol_raw).items()}
            else:
                phases_vol = {k: v * 1e6 for k, v in
                              filter_near_zero(dict(zip(phase_names, vol_raw))).items()}
        except (AttributeError, Exception):
            pass

        # Phase masses (kg -> g)
        phases_mass = {}
        try:
            mass_raw = engine.phases_mass
            if isinstance(mass_raw, dict):
                phases_mass = {k: v * 1e3 for k, v in filter_near_zero(mass_raw).items()}
            else:
                phases_mass = {k: v * 1e3 for k, v in
                               filter_near_zero(dict(zip(phase_names, mass_raw))).items()}
        except (AttributeError, Exception):
            pass

        # Phase volume fractions
        phases_vol_frac = {}
        try:
            vfrac_raw = engine.phases_volume_frac
            if isinstance(vfrac_raw, dict):
                phases_vol_frac = filter_near_zero(vfrac_raw)
            else:
                phases_vol_frac = filter_near_zero(dict(zip(phase_names, vfrac_raw)))
        except (AttributeError, Exception):
            pass

        # Solids mass and volume fractions
        solids_mf = {}
        solids_vf = {}
        try:
            smf_raw = engine.solids_mass_frac
            if isinstance(smf_raw, dict):
                solids_mf = filter_near_zero(smf_raw)
            else:
                solids_mf = filter_near_zero(dict(zip(phase_names, smf_raw)))
        except (AttributeError, Exception):
            pass
        try:
            svf_raw = engine.solids_volume_frac
            if isinstance(svf_raw, dict):
                solids_vf = filter_near_zero(svf_raw)
            else:
                solids_vf = filter_near_zero(dict(zip(phase_names, svf_raw)))
        except (AttributeError, Exception):
            pass

        # Aqueous species molarity (mol/L)
        aq_molarity = {}
        try:
            aqm_raw = engine.aq_species_molarity
            if isinstance(aqm_raw, dict):
                aq_molarity = filter_near_zero(aqm_raw)
            else:
                aq_molarity = filter_near_zero(dict(zip(engine.species_names, aqm_raw)))
        except (AttributeError, Exception):
            pass

        # All species moles
        species_moles = {}
        try:
            sm_raw = engine.species_moles
            if isinstance(sm_raw, dict):
                species_moles = filter_near_zero(sm_raw)
            else:
                species_moles = filter_near_zero(dict(zip(engine.species_names, sm_raw)))
        except (AttributeError, Exception):
            pass

        result = {
            "status": "success",
            "conditions": {"T_K": T, "P_Pa": P},
            "system": {
                "pH": engine.pH,
                "pE": engine.pE,
                "ionic_strength": engine.ionic_strength,
                "volume_m3": engine.system_volume,
                "mass_kg": engine.system_mass,
            },
            "phases": {
                "names": list(active_phases.keys()),
                "moles": list(active_phases.values()),
                "volume_cm3": [phases_vol.get(n, 0.0) for n in active_phases],
                "mass_g": [phases_mass.get(n, 0.0) for n in active_phases],
                "volume_frac": [phases_vol_frac.get(n, 0.0) for n in active_phases],
            },
            "saturation_indices": sat_indices,
        }

        if aq_molality or aq_molarity:
            aq = {}
            if aq_molality:
                aq["molality"] = aq_molality
            if aq_molarity:
                aq["molarity"] = aq_molarity
            result["aqueous_species"] = aq

        if species_moles:
            result["species"] = {"moles": species_moles}

        if solids_mf or solids_vf:
            solids = {}
            if solids_mf:
                solids["mass_frac"] = solids_mf
            if solids_vf:
                solids["volume_frac"] = solids_vf
            result["solids"] = solids

        # Diagnostics: system dimensions
        try:
            result["diagnostics"] = {
                "n_elements": engine.nelements,
                "n_phases": engine.nphases,
                "n_species": engine.nspecies,
            }
        except (AttributeError, Exception):
            pass

        # Composition metadata: molar masses and volumes
        try:
            result["composition"] = {
                "element_molar_masses": dict(zip(engine.element_names, engine.element_molar_masses))
                if not isinstance(engine.element_molar_masses, dict)
                else engine.element_molar_masses,
                "phase_molar_volume": dict(zip(phase_names, engine.phases_molar_volume))
                if not isinstance(engine.phases_molar_volume, dict)
                else engine.phases_molar_volume,
            }
        except (AttributeError, Exception):
            pass

        # Element balance: partitioning between aqueous and solid phases
        try:
            result["element_balance"] = {
                "aqueous": dict(zip(engine.element_names, engine.aq_elements_amounts))
                if not isinstance(engine.aq_elements_amounts, dict)
                else engine.aq_elements_amounts,
                "solid": dict(zip(engine.element_names, engine.solid_elements_amounts))
                if not isinstance(engine.solid_elements_amounts, dict)
                else engine.solid_elements_amounts,
            }
        except (AttributeError, Exception):
            pass

        return result


class GemsExplorer:
    """Utility to explore available GEMS projects and databases."""

    @staticmethod
    def list_systems() -> list[str]:
        """List pre-packaged system names."""
        return list_available_systems()

    @staticmethod
    def system_info(system_name: str) -> dict[str, Any]:
        """Get metadata about a pre-packaged system without running equilibrium."""
        lst_path = find_system_dat_lst(system_name)
        work_dir = lst_path.parent

        ChemicalEngineDicts = check_xgems()
        with _cwd_lock:
            old_cwd = os.getcwd()
            try:
                os.chdir(str(work_dir))
                engine = ChemicalEngineDicts(str(lst_path))
            finally:
                os.chdir(old_cwd)

        return {
            "system": system_name,
            "lst_path": str(lst_path),
            "T_K": engine.T,
            "P_Pa": engine.P,
            "elements": engine.element_names,
            "n_elements": engine.nelements,
            "phases": engine.phase_names,
            "n_phases": engine.nphases,
            "n_species": engine.nspecies,
        }
