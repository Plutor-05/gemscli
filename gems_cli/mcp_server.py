"""MCP Server exposing GEMS thermodynamic simulation as tools for AI Agents.

Usage:
    gems-mcp                    # stdio transport (default for MCP clients)
    gems-mcp --transport sse --port 8765
"""

from __future__ import annotations

from typing import Any

from gems_cli.engine import GemsEngine, GemsExplorer
from gems_cli.utils import validate_bulk_composition

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "mcp package required for MCP server. Install via:\n"
        "  pip install mcp\n"
        "Or: pip install gemscli[mcp]"
    )

mcp = FastMCP("gems-thermodynamics")


def _error_response(message: str, details: dict[str, Any] | None = None) -> dict:
    """Build a structured error response."""
    resp = {"status": "error", "message": message}
    if details:
        resp["details"] = details
    return resp


@mcp.tool()
def gems_equilibrate(
    system: str,
    T_celsius: float = 25.0,
    P_bar: float = 1.0,
    bulk_composition: dict[str, float] = {},
    suppress_species: list[str] = [],
    suppress_phases: list[str] = [],
) -> dict[str, Any]:
    """Run a Gibbs Energy Minimization equilibrium calculation.

    Args:
        system: Pre-packaged system name (e.g. 'calcite', 'cement_hydration'). Use gems_list_systems to see available systems.
        T_celsius: Temperature in degrees Celsius (default 25).
        P_bar: Pressure in bar (default 1.0).
        bulk_composition: Element amounts as {symbol: moles}, e.g. {"Ca": 0.01, "H": 111.0, "O": 55.5}. If empty, uses the system's default composition.
        suppress_species: Optional list of species names to exclude from calculation.
        suppress_phases: Optional list of phase names to exclude from calculation.

    Returns:
        Equilibrium results including pH, phase assemblage, saturation indices.
    """
    try:
        engine = GemsEngine(system_name=system)
        kwargs: dict[str, Any] = {
            "T_celsius": T_celsius,
            "P_bar": P_bar,
        }
        if bulk_composition:
            kwargs["bulk_composition"] = bulk_composition
        if suppress_species:
            kwargs["suppress_species"] = suppress_species
        if suppress_phases:
            kwargs["suppress_phases"] = suppress_phases
        return engine.equilibrate(**kwargs)
    except FileNotFoundError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(f"Simulation failed: {e}")


@mcp.tool()
def gems_list_systems() -> dict[str, Any]:
    """List all available pre-packaged simulation systems.

    Returns a list of system names that can be used with gems_equilibrate and gems_system_info.
    """
    systems = GemsExplorer.list_systems()
    return {"systems": systems, "count": len(systems)}


@mcp.tool()
def gems_system_info(system: str) -> dict[str, Any]:
    """Get metadata about a simulation system without running equilibrium.

    Shows available elements, phases, species counts, and default conditions.
    Use this before gems_equilibrate to understand what elements and phases are available.

    Args:
        system: Pre-packaged system name (e.g. 'calcite').
    """
    try:
        return GemsExplorer.system_info(system)
    except FileNotFoundError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(f"Failed to get system info: {e}")


@mcp.tool()
def gems_validate(
    system: str,
    T_celsius: float = 25.0,
    P_bar: float = 1.0,
    bulk_composition: dict[str, float] = {},
) -> dict[str, Any]:
    """Pre-flight validation of simulation inputs without running equilibrium.

    Checks that bulk_composition is valid for the target system: no zero-valued
    elements (which silently break xgems), no unknown elements, and reasonable
    T/P bounds. Always call this before gems_equilibrate when composing inputs
    for the first time.

    Args:
        system: Pre-packaged system name (e.g. 'calcite').
        T_celsius: Temperature in Celsius (default 25).
        P_bar: Pressure in bar (default 1.0).
        bulk_composition: Element amounts as {symbol: moles}.

    Returns:
        { valid: bool, warnings: list[str], system_elements: list[str] }.
    """
    try:
        info = GemsExplorer.system_info(system)
    except FileNotFoundError as e:
        return _error_response(str(e))
    except Exception as e:
        return _error_response(f"Failed to load system: {e}")

    system_elements = info["elements"]
    warnings: list[str] = []

    if bulk_composition:
        valid, bulk_warnings = validate_bulk_composition(
            bulk_composition, system_elements=system_elements,
        )
        warnings.extend(bulk_warnings)
    else:
        valid = True

    # Physical bounds check
    if T_celsius < -273.15:
        valid = False
        warnings.append(f"T_celsius={T_celsius} is below absolute zero (-273.15 °C).")
    elif T_celsius > 2000:
        warnings.append(f"T_celsius={T_celsius} is very high — verify this is intentional.")

    if P_bar <= 0:
        valid = False
        warnings.append(f"P_bar={P_bar} must be positive.")
    elif P_bar > 1e5:
        warnings.append(f"P_bar={P_bar} is very high — verify this is intentional.")

    return {
        "valid": valid,
        "warnings": warnings,
        "system_elements": system_elements,
    }


@mcp.tool()
def gems_batch_tp_scan(
    system: str,
    T_range_celsius: list[float] = [25.0, 50.0, 75.0, 100.0],
    P_bar: float = 1.0,
    bulk_composition: dict[str, float] = {},
    suppress_species: list[str] = [],
    suppress_phases: list[str] = [],
) -> dict[str, Any]:
    """Run equilibrium at multiple temperatures to produce a T-scan.

    Useful for studying how phase assemblage and pH change with temperature.

    Args:
        system: Pre-packaged system name.
        T_range_celsius: List of temperatures in Celsius, e.g. [25, 50, 75, 100].
        P_bar: Fixed pressure in bar.
        bulk_composition: Element amounts as {symbol: moles}.
        suppress_species: Optional list of species names to exclude from calculation.
        suppress_phases: Optional list of phase names to exclude from calculation.

    Returns:
        Results at each temperature point.
    """
    results = []
    for t_c in T_range_celsius:
        try:
            engine = GemsEngine(system_name=system)
            kwargs: dict[str, Any] = {"T_celsius": t_c, "P_bar": P_bar}
            if bulk_composition:
                kwargs["bulk_composition"] = bulk_composition
            if suppress_species:
                kwargs["suppress_species"] = suppress_species
            if suppress_phases:
                kwargs["suppress_phases"] = suppress_phases
            result = engine.equilibrate(**kwargs)
            result["T_celsius_input"] = t_c
            results.append(result)
        except Exception as e:
            results.append({
                "status": "error",
                "T_celsius_input": t_c,
                "message": str(e),
            })

    return {
        "system": system,
        "P_bar": P_bar,
        "n_points": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# New tools for agent-driven research workflows
# ---------------------------------------------------------------------------


def _detect_transitions(results: list[dict], variable: str) -> list[dict]:
    """Detect phase appearance/disappearance across a sweep result list.

    Returns a list of transition dicts with phase name, event type,
    index, and the variable value at the transition point.
    """
    transitions = []
    # Collect all phase names seen across all results
    all_phases = set()
    for r in results:
        if r.get("status") == "success" and "phases" in r:
            all_phases.update(r["phases"].get("names", []))

    for phase in sorted(all_phases):
        prev_present = None
        for i, r in enumerate(results):
            if r.get("status") != "success" or "phases" not in r:
                prev_present = None  # reset across error gaps
                continue
            present = phase in r["phases"].get("names", [])
            if prev_present is not None and present != prev_present:
                event = "appears" if present else "disappears"
                transitions.append({
                    "phase": phase,
                    "event": event,
                    "at_index": i,
                    "variable_value": r.get("T_celsius_input", r.get("var_value")),
                })
            prev_present = present
    return transitions


@mcp.tool()
def gems_sweep(
    system: str,
    variable: str,
    var_range: list[float],
    T_celsius: float = 25.0,
    P_bar: float = 1.0,
    bulk_composition: dict[str, float] = {},
    suppress_species: list[str] = [],
    suppress_phases: list[str] = [],
) -> dict[str, Any]:
    """Run equilibrium across a range of values for any single variable.

    Supports scanning temperature (variable="T_celsius"), pressure
    (variable="P_bar"), or any element composition (variable="C", "Ca", etc.).

    Automatically detects phase transitions (appearance/disappearance) and
    includes them in the response.

    Args:
        system: Pre-packaged system name.
        variable: Which parameter to sweep. "T_celsius" for temperature,
                  "P_bar" for pressure, or an element symbol (e.g. "C", "Ca")
                  to sweep that element's moles in bulk_composition.
        var_range: List of values to sweep over.
        T_celsius: Base temperature (used when variable is not "T_celsius").
        P_bar: Base pressure (used when variable is not "P_bar").
        bulk_composition: Base element composition (used when variable is an element).
        suppress_species: Optional species to exclude.
        suppress_phases: Optional phases to exclude.

    Returns:
        Sweep results with per-point equilibrium data and detected transitions.
    """
    # Validate variable name
    valid_variables = {"T_celsius", "P_bar"}
    if variable not in valid_variables:
        # Treat as element symbol — check it's a reasonable name (1-2 alpha chars)
        if not variable.isalpha() or len(variable) > 2:
            return {
                "error": f"Invalid variable '{variable}'. Use 'T_celsius', 'P_bar', "
                         f"or a 1-2 letter element symbol (e.g. 'C', 'Ca', 'Fe')."
            }

    results = []
    for val in var_range:
        try:
            engine = GemsEngine(system_name=system)
            kwargs: dict[str, Any] = {}
            bulk = dict(bulk_composition) if bulk_composition else {}

            if variable == "T_celsius":
                kwargs["T_celsius"] = val
                kwargs["P_bar"] = P_bar
            elif variable == "P_bar":
                kwargs["T_celsius"] = T_celsius
                kwargs["P_bar"] = val
            else:
                # Treat as element symbol
                bulk[variable] = val
                kwargs["T_celsius"] = T_celsius
                kwargs["P_bar"] = P_bar

            if bulk:
                kwargs["bulk_composition"] = bulk
            if suppress_species:
                kwargs["suppress_species"] = suppress_species
            if suppress_phases:
                kwargs["suppress_phases"] = suppress_phases

            result = engine.equilibrate(**kwargs)
            result["var_value"] = val
            results.append(result)
        except Exception as e:
            results.append({
                "status": "error",
                "var_value": val,
                "message": str(e),
            })

    transitions = _detect_transitions(results, variable)

    return {
        "system": system,
        "variable": variable,
        "var_range": var_range,
        "n_points": len(results),
        "results": results,
        "transitions": transitions,
    }


@mcp.tool()
def gems_diagnose(results: dict) -> dict[str, Any]:
    """Diagnose quality and physical meaning of batch sweep results.

    Checks for convergence oscillations, pH jumps, phase transitions,
    and saturation index crossings.

    Args:
        results: A batch sweep result dict (from gems_sweep or
                 gems_batch_tp_scan) containing a "results" list.

    Returns:
        Quality diagnostics, phase transitions, and SI crossings.
    """
    result_list = results.get("results", [])
    if not result_list:
        return {"error": "No results to diagnose"}

    quality = {
        "total_points": len(result_list),
        "success_count": 0,
        "error_count": 0,
        "convergence_issues": [],
        "pH_jumps": [],
        "oscillation_suspects": [],
    }

    # Collect data series for analysis
    pH_series = []
    phase_mole_series = []  # list of dicts: {phase_name: moles}
    si_series = []

    for i, r in enumerate(result_list):
        if r.get("status") == "success":
            quality["success_count"] += 1
            pH_series.append((i, r.get("system", {}).get("pH")))
            # Build phase mole dict
            if "phases" in r:
                names = r["phases"].get("names", [])
                moles = r["phases"].get("moles", [])
                phase_mole_series.append((i, dict(zip(names, moles))))
            else:
                phase_mole_series.append((i, {}))
            # Build SI dict
            si_series.append((i, r.get("saturation_indices", {})))
        else:
            quality["error_count"] += 1
            quality["convergence_issues"].append(i)

    # pH jump detection (delta > 2.0 between adjacent successful points)
    for j in range(1, len(pH_series)):
        idx_prev, ph_prev = pH_series[j - 1]
        idx_curr, ph_curr = pH_series[j]
        if ph_prev is not None and ph_curr is not None:
            delta = abs(ph_curr - ph_prev)
            if delta > 2.0:
                quality["pH_jumps"].append({
                    "from_index": idx_prev,
                    "to_index": idx_curr,
                    "delta_pH": round(delta, 2),
                })

    # Oscillation detection: look for 0 -> large -> 0 patterns in any phase
    all_phase_names = set()
    for _, pm in phase_mole_series:
        all_phase_names.update(pm.keys())

    for phase_name in all_phase_names:
        values = [(i, pm.get(phase_name, 0.0)) for i, pm in phase_mole_series]
        for k in range(1, len(values) - 1):
            _, v_prev = values[k - 1]
            _, v_curr = values[k]
            _, v_next = values[k + 1]
            if v_prev < 0.01 and v_curr > 0.5 and v_next < 0.01:
                idx = values[k][0]
                if idx not in quality["oscillation_suspects"]:
                    quality["oscillation_suspects"].append(idx)

    # Phase transitions
    phase_transitions = _detect_transitions(result_list, results.get("variable", ""))

    # SI crossing detection
    si_crossings = []
    all_si_phases = set()
    for _, si in si_series:
        all_si_phases.update(si.keys())

    for phase_name in all_si_phases:
        prev_si = None
        prev_idx = None
        for idx, si in si_series:
            curr_si = si.get(phase_name)
            if curr_si is not None and prev_si is not None:
                if (prev_si > 0) != (curr_si > 0):
                    si_crossings.append({
                        "phase": phase_name,
                        "event": "SI_crosses_zero",
                        "at_index": idx,
                        "prev_SI": round(prev_si, 3),
                        "new_SI": round(curr_si, 3),
                    })
            if curr_si is not None:
                prev_si = curr_si
                prev_idx = idx

    return {
        "quality": quality,
        "phase_transitions": phase_transitions,
        "si_crossings": si_crossings,
    }


@mcp.tool()
def gems_analyze_species(
    results: dict,
    elements: list[str] = [],
    top_n: int = 10,
) -> dict[str, Any]:
    """Extract and rank aqueous species by concentration from batch results.

    Filters species by element membership and ranks by molality.

    Args:
        results: A batch sweep result dict (from gems_sweep) containing
                 a "results" list with aqueous_species data.
        elements: List of element symbols to filter by (e.g. ["Al", "Fe"]).
                  If empty, returns all species.
        top_n: Maximum number of species to return per element.

    Returns:
        Per-element ranked species list with molality values across the sweep.
    """
    result_list = results.get("results", [])
    if not result_list:
        return {"error": "No results to analyze"}

    # Helper: check if a species name contains an element symbol
    def species_contains_element(species_name: str, elem: str) -> bool:
        import re
        # Match element symbol bounded by non-alpha chars or string boundaries
        # e.g. "Al" matches in "Al(OH)4-" but not in "NaCl"
        pattern = r'(?<![a-zA-Z])' + re.escape(elem) + r'(?![a-zA-Z])'
        return bool(re.search(pattern, species_name))

    # Collect species data across all successful points
    all_species_data = {}  # species_name -> [(index, molality)]
    for i, r in enumerate(result_list):
        if r.get("status") != "success":
            continue
        aq = r.get("aqueous_species", {})
        molality = aq.get("molality", {})
        for sp, mol in molality.items():
            if sp not in all_species_data:
                all_species_data[sp] = []
            all_species_data[sp].append((i, mol))

    # Filter by elements if specified
    if elements:
        filtered = {}
        for sp, data in all_species_data.items():
            for elem in elements:
                if species_contains_element(sp, elem):
                    filtered[sp] = data
                    break
        species_to_rank = filtered
    else:
        species_to_rank = all_species_data

    # Rank by max molality across the sweep
    ranked = []
    for sp, data in species_to_rank.items():
        max_mol = max((m for _, m in data), default=0.0)
        avg_mol = sum(m for _, m in data) / len(data) if data else 0.0
        ranked.append({
            "species": sp,
            "max_molality": max_mol,
            "avg_molality": avg_mol,
            "data_points": len(data),
        })
    ranked.sort(key=lambda x: x["max_molality"], reverse=True)
    ranked = ranked[:top_n]

    return {
        "elements_filter": elements,
        "top_n": top_n,
        "species": ranked,
    }


@mcp.tool()
def gems_interpret(result: dict, context: str = "") -> dict[str, Any]:
    """Provide a structured summary of a single equilibrium result.

    Extracts key facts: pH classification, dominant phases, SI status,
    element distribution, and suggests follow-up analyses. The structured
    output is designed for an AI agent to build physical interpretations upon.

    Args:
        result: A single equilibrium result dict (from gems_equilibrate).
        context: Optional context string (e.g. "ferrite carbonation study").

    Returns:
        Structured summary with key_findings, warnings, and suggestions.
    """
    if result.get("status") != "success":
        return {
            "summary": f"Calculation failed: {result.get('message', 'unknown error')}",
            "key_findings": [],
            "warnings": ["Result status is not success"],
            "suggestions": ["Check input parameters and system configuration"],
        }

    sys_ = result.get("system", {})
    phases = result.get("phases", {})
    si = result.get("saturation_indices", {})
    aq = result.get("aqueous_species", {})
    elem_bal = result.get("element_balance", {})
    diag = result.get("diagnostics", {})

    pH = sys_.get("pH")
    ionic_strength = sys_.get("ionic_strength")

    # pH classification
    if pH is not None:
        if pH < 6.5:
            ph_desc = f"pH {pH:.1f}, acidic"
        elif pH < 7.5:
            ph_desc = f"pH {pH:.1f}, near-neutral"
        elif pH < 10:
            ph_desc = f"pH {pH:.1f}, moderately alkaline"
        else:
            ph_desc = f"pH {pH:.1f}, strongly alkaline"
    else:
        ph_desc = "pH not available"

    # Phase summary
    phase_names = phases.get("names", [])
    phase_moles = phases.get("moles", [])
    dominant_phase = ""
    if phase_names and phase_moles:
        max_idx = phase_moles.index(max(phase_moles))
        dominant_phase = phase_names[max_idx]

    # SI summary
    supersaturated = [p for p, v in si.items() if v > 0.1]
    undersaturated = [p for p, v in si.items() if v < -0.5]

    # Key findings
    findings = [f"{ph_desc}, ionic strength {ionic_strength:.4f} mol/kg" if ionic_strength is not None else ph_desc]
    if dominant_phase:
        findings.append(f"Dominant phase: {dominant_phase} ({phase_moles[max_idx]:.4f} mol)")
    if supersaturated:
        findings.append(f"Supersaturated phases: {', '.join(supersaturated)}")
    if undersaturated:
        findings.append(f"Undersaturated phases: {', '.join(undersaturated)}")

    # Top aqueous species
    molality = aq.get("molality", {})
    if molality:
        top_sp = sorted(molality.items(), key=lambda x: x[1], reverse=True)[:3]
        sp_str = ", ".join(f"{k} ({v:.4f})" for k, v in top_sp)
        findings.append(f"Top aqueous species: {sp_str}")

    # Element balance
    if elem_bal:
        aq_bal = elem_bal.get("aqueous", {})
        solid_bal = elem_bal.get("solid", {})
        if aq_bal and solid_bal:
            total_elements = set(list(aq_bal.keys()) + list(solid_bal.keys()))
            imbalanced = []
            for el in total_elements:
                aq_amt = aq_bal.get(el, 0)
                sol_amt = solid_bal.get(el, 0)
                total = aq_amt + sol_amt
                if total > 0:
                    aq_frac = aq_amt / total
                    if aq_frac > 0.95:
                        imbalanced.append(f"{el} almost entirely in aqueous phase ({aq_frac:.0%})")
                    elif aq_frac < 0.05:
                        imbalanced.append(f"{el} almost entirely in solid phase ({1-aq_frac:.0%})")
            if imbalanced:
                findings.append("Element distribution: " + "; ".join(imbalanced[:3]))

    # Warnings
    warnings = []
    if pH is not None and pH > 13:
        warnings.append("Very high pH — verify bulk composition is realistic")
    if ionic_strength and ionic_strength > 1.0:
        warnings.append("High ionic strength — activity model may be less accurate")

    # Suggestions
    suggestions = []
    if supersaturated:
        suggestions.append(f"Consider suppressing {supersaturated[0]} to explore metastable assemblage")
    if not supersaturated and not undersaturated:
        suggestions.append("All phases near saturation — system is well-equilibrated")
    if pH is not None and 6 < pH < 8:
        suggestions.append("Neutral pH range — good candidate for environmental leaching studies")

    return {
        "summary": f"{ph_desc}. {len(phase_names)} phases active. {len(molality)} aqueous species.",
        "key_findings": findings,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="gems-mcp",
                                     description="GEMS MCP Server for AI Agent integration")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="Transport type (default: stdio)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Port for SSE transport (default: 8765)")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
