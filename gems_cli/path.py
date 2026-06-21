"""Path calculation engine wrapping xGEMS ChemicalEngine.

Provides PathCalculator: a sequential equilibrium calculator that supports
warm-start carry-forward, enabling true path calculations (e.g. leaching
simulations across L/S ratios spanning orders of magnitude).

Unlike GemsEngine (which wraps ChemicalEngineDicts), PathCalculator uses the
low-level ChemicalEngine API which exposes reequilibrate(), setB(), and other
methods required for path calculations.
"""

from __future__ import annotations

import os
from typing import Any

from gems_cli import check_xgems_lowlevel
from gems_cli.engine import _cwd_lock
from gems_cli.utils import (
    bar_to_pascal,
    celsius_to_kelvin,
    filter_near_zero,
    find_system_dat_lst,
)

# reequilibrate() return codes
_REEQUILIBRATE_OK = {0, 2, 6}  # 0=no change, 2=OK-AIA, 6=OK-SIA
_REEQUILIBRATE_BAD = {3, 7}  # 3=bad-AIA, 7=bad-SIA


def _build_b_vector(engine, bulk_composition: dict[str, float]) -> list[float]:
    """Convert a partial {element: moles} dict to a full b-vector.

    Starts from the engine's current element amounts (from the DBR file),
    then overlays values from bulk_composition for matching element names.

    Args:
        engine: A ChemicalEngine instance.
        bulk_composition: {element_symbol: moles}. Only non-zero elements
            should be included.

    Returns:
        List of floats with length engine.numElements(), aligned with the
        engine's internal element ordering.
    """
    b = list(engine.elementAmounts())
    for elem, value in bulk_composition.items():
        try:
            idx = engine.indexElement(elem)
            b[idx] = value
        except (ValueError, RuntimeError):
            pass  # skip unknown elements
    return b


class PathCalculator:
    """Sequential/path calculation wrapper around xgems ChemicalEngine.

    Uses the low-level ChemicalEngine API which supports:
    - equilibrate(T, P, b) with explicit b-vector
    - reequilibrate(warmstart) for warm-start carry-forward
    - setB() / setPT() for state mutation between steps
    - Species bounds for preventing phase dropping at extreme conditions

    Usage::

        calc = PathCalculator("calcite")
        calc.set_conditions(T_celsius=25, P_bar=1.0)

        # Single-point equilibrium
        result = calc.equilibrate(bulk_composition={"Ca": 0.01, "C": 0.01, "H": 111.0, "O": 55.5})

        # Multi-step path with warm-start
        for bulk in bulk_sequence:
            result = calc.step(bulk_composition=bulk, warmstart=True)
    """

    def __init__(
        self,
        system_name: str | None = None,
        lst_path: str | None = None,
    ):
        """Initialize from a pre-packaged system name or explicit .lst path.

        Args:
            system_name: Name of a system in data/systems/ (e.g. "calcite").
            lst_path: Direct path to a GEMS3K *-dat.lst file.
        """
        if system_name:
            self._lst_path = find_system_dat_lst(system_name)
            self._system_name = system_name
            self._work_dir = self._lst_path.parent
        elif lst_path:
            from pathlib import Path as _Path

            self._lst_path = _Path(lst_path)
            self._system_name = self._lst_path.stem.replace("-dat", "")
            self._work_dir = self._lst_path.parent
        else:
            raise ValueError("Provide either system_name or lst_path.")

        if not self._lst_path.exists():
            raise FileNotFoundError(f"lst file not found: {self._lst_path}")

        self._engine = None  # lazy init
        self._T = 298.15
        self._P = 1e5
        self._default_b = None

    @property
    def system_name(self) -> str:
        return self._system_name

    def _ensure_engine(self):
        """Create the ChemicalEngine instance if not yet created."""
        if self._engine is not None:
            return
        ChemicalEngine = check_xgems_lowlevel()
        with _cwd_lock:
            old_cwd = os.getcwd()
            try:
                os.chdir(str(self._work_dir))
                self._engine = ChemicalEngine(str(self._lst_path))
            finally:
                os.chdir(old_cwd)
        self._default_b = list(self._engine.elementAmounts())

    @property
    def element_names(self) -> list[str]:
        """Element names in the system's internal ordering."""
        self._ensure_engine()
        return [self._engine.elementName(i) for i in range(self._engine.numElements())]

    @property
    def phase_names(self) -> list[str]:
        """Phase names in the system's internal ordering."""
        self._ensure_engine()
        return [self._engine.phaseName(i) for i in range(self._engine.numPhases())]

    @property
    def species_names(self) -> list[str]:
        """Species names in the system's internal ordering."""
        self._ensure_engine()
        return [self._engine.speciesName(i) for i in range(self._engine.numSpecies())]

    def set_conditions(
        self,
        T: float = 298.15,
        P: float = 1e5,
        T_celsius: float | None = None,
        P_bar: float | None = None,
    ) -> None:
        """Set temperature and pressure for subsequent calculations.

        Args:
            T: Temperature in Kelvin (default 298.15).
            P: Pressure in Pascal (default 1e5).
            T_celsius: Alternative temperature in Celsius (overrides T).
            P_bar: Alternative pressure in bar (overrides P).
        """
        if T_celsius is not None:
            T = celsius_to_kelvin(T_celsius)
        if P_bar is not None:
            P = bar_to_pascal(P_bar)
        self._T = T
        self._P = P

    def set_species_lower_limits(self, limits: dict[str, float]) -> None:
        """Set lower bounds on species amounts (prevents phase dropping).

        Args:
            limits: {species_name: min_amount} dict.
        """
        self._ensure_engine()
        for name, amount in limits.items():
            self._engine.setSpeciesLowerLimit(name, amount)

    def set_species_upper_limits(self, limits: dict[str, float]) -> None:
        """Set upper bounds on species amounts.

        Args:
            limits: {species_name: max_amount} dict.
        """
        self._ensure_engine()
        for name, amount in limits.items():
            self._engine.setSpeciesUpperLimit(name, amount)

    def equilibrate(
        self,
        bulk_composition: dict[str, float],
        T: float | None = None,
        P: float | None = None,
        T_celsius: float | None = None,
        P_bar: float | None = None,
    ) -> dict[str, Any]:
        """Run a single-point equilibrium calculation.

        Args:
            bulk_composition: {element_symbol: moles} dict.
            T: Temperature in Kelvin (overrides set_conditions).
            P: Pressure in Pascal (overrides set_conditions).
            T_celsius: Temperature in Celsius (overrides T).
            P_bar: Pressure in bar (overrides P).

        Returns:
            Structured result dict (same schema as GemsEngine.equilibrate).
        """
        self._ensure_engine()

        if T_celsius is not None:
            T = celsius_to_kelvin(T_celsius)
        if P_bar is not None:
            P = bar_to_pascal(P_bar)
        t = T if T is not None else self._T
        p = P if P is not None else self._P

        b = _build_b_vector(self._engine, bulk_composition)
        self._engine.equilibrate(t, p, b)

        result = self._extract_results(t, p)
        result["path_info"] = {
            "converged": self._engine.converged(),
            "num_iterations": self._engine.numIterations(),
        }
        return result

    def step(
        self,
        bulk_composition: dict[str, float] | None = None,
        T: float | None = None,
        P: float | None = None,
        T_celsius: float | None = None,
        P_bar: float | None = None,
        warmstart: bool = True,
    ) -> dict[str, Any]:
        """Advance one path step with warm-start carry-forward.

        Modifies bulk composition and/or T/P on the existing engine,
        then reequilibrate from the previous solution state.

        Args:
            bulk_composition: {element_symbol: moles} dict (optional).
            T: Temperature in Kelvin (optional).
            P: Pressure in Pascal (optional).
            T_celsius: Temperature in Celsius (overrides T).
            P_bar: Pressure in bar (overrides P).
            warmstart: If True, use warm-start (SIA). If False, cold-start (AIA).

        Returns:
            Structured result dict with additional path_info key.
        """
        self._ensure_engine()

        # Apply bulk composition change
        if bulk_composition is not None:
            b = _build_b_vector(self._engine, bulk_composition)
            self._engine.setB(b)

        # Apply T/P change
        if T_celsius is not None:
            T = celsius_to_kelvin(T_celsius)
        if P_bar is not None:
            P = bar_to_pascal(P_bar)
        t = T if T is not None else self._T
        p = P if P is not None else self._P
        self._engine.setPT(t, p)

        # Reequilibrate
        status = self._engine.reequilibrate(warmstart)
        converged = self._engine.converged()

        # Fallback: retry with cold start if warm-start failed
        if status in _REEQUILIBRATE_BAD or not converged:
            if warmstart:
                self._engine.setColdStart()
                status = self._engine.reequilibrate(False)
                converged = self._engine.converged()
                warmstart = False

        result = self._extract_results(t, p)
        result["path_info"] = {
            "reequilibrate_status": status,
            "warmstart_used": warmstart,
            "converged": converged,
            "num_iterations": self._engine.numIterations(),
        }
        return result

    def run_path(
        self,
        bulk_sequence: list[dict[str, float]],
        T_celsius: float | None = None,
        P_bar: float | None = None,
        warmstart: bool = True,
    ) -> list[dict[str, Any]]:
        """Run a sequence of equilibrium steps with warm-start.

        The first step uses equilibrate() (cold start), subsequent steps
        use step() with warm-start carry-forward.

        Args:
            bulk_sequence: List of {element: moles} dicts.
            T_celsius: Temperature in Celsius (optional).
            P_bar: Pressure in bar (optional).
            warmstart: Whether to use warm-start for all steps after the first.

        Returns:
            List of result dicts.
        """
        results = []
        for i, bulk in enumerate(bulk_sequence):
            if i == 0:
                r = self.equilibrate(
                    bulk_composition=bulk,
                    T_celsius=T_celsius,
                    P_bar=P_bar,
                )
            else:
                r = self.step(
                    bulk_composition=bulk,
                    T_celsius=T_celsius,
                    P_bar=P_bar,
                    warmstart=warmstart,
                )
            results.append(r)
        return results

    def export_dbr_state(self) -> str:
        """Export current engine state as a DBR JSON string."""
        self._ensure_engine()
        return self._engine.writeDbrToJsonString()

    def load_dbr_state(self, json_string: str) -> None:
        """Load engine state from a DBR JSON string."""
        self._ensure_engine()
        self._engine.readDbrFromJsonString(json_string)

    def _extract_results(self, T: float, P: float) -> dict[str, Any]:
        """Extract all available results into a structured dictionary.

        Returns a dict compatible with GemsEngine._extract_results output.
        """
        eng = self._engine
        n_ph = eng.numPhases()
        n_sp = eng.numSpecies()

        phase_names = [eng.phaseName(i) for i in range(n_ph)]
        species_names = [eng.speciesName(i) for i in range(n_sp)]

        # Phase amounts
        phase_amounts = eng.phaseAmounts()
        phases_moles = dict(zip(phase_names, phase_amounts))
        active_phases = filter_near_zero(phases_moles)

        # Phase volumes (m3 -> cm3)
        phases_vol_arr = eng.phaseVolumes()
        phases_vol = {k: v * 1e6 for k, v in
                      filter_near_zero(dict(zip(phase_names, phases_vol_arr))).items()}

        # Phase masses (kg -> g)
        phases_mass_arr = eng.phaseMasses()
        phases_mass = {k: v * 1e3 for k, v in
                       filter_near_zero(dict(zip(phase_names, phases_mass_arr))).items()}

        # Saturation indices
        sat_arr = eng.phaseSatIndices()
        sat_indices = dict(zip(phase_names, sat_arr))

        # Species molality
        aq_molality = {}
        try:
            mol_arr = eng.speciesMolalities()
            aq_molality = filter_near_zero(dict(zip(species_names, mol_arr)))
        except (AttributeError, RuntimeError):
            pass

        # Activity coefficients
        ln_gam = {}
        try:
            gam_arr = eng.lnActivityCoefficients()
            ln_gam = dict(zip(species_names, gam_arr))
        except (AttributeError, RuntimeError):
            pass

        result = {
            "status": "success",
            "conditions": {"T_K": T, "P_Pa": P},
            "system": {
                "pH": eng.pH(),
                "pE": eng.pe(),
                "ionic_strength": eng.ionicStrength(),
                "volume_m3": eng.systemVolume(),
                "mass_kg": eng.systemMass(),
            },
            "phases": {
                "names": list(active_phases.keys()),
                "moles": list(active_phases.values()),
                "volume_cm3": [phases_vol.get(n, 0.0) for n in active_phases],
                "mass_g": [phases_mass.get(n, 0.0) for n in active_phases],
            },
            "saturation_indices": sat_indices,
        }

        if aq_molality:
            result["aqueous_species"] = {"molality": aq_molality}

        if ln_gam:
            result["activity_coefficients"] = {
                "ln_gamma": filter_near_zero(ln_gam)
            }

        # Diagnostics
        result["diagnostics"] = {
            "n_elements": eng.numElements(),
            "n_phases": n_ph,
            "n_species": n_sp,
        }

        return result
