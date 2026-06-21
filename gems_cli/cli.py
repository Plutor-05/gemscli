"""CLI entry point for GEMS thermodynamic simulation.

Usage:
    gems-cli --list-systems
    gems-cli --system-info calcite
    gems-cli --input input.json [--output results.json]
    gems-cli --system calcite --T 25 --P 1 --bulk-composition '{"Ca":0.01,"H":111,"O":55.5}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gems_cli.engine import GemsEngine, GemsExplorer
from gems_cli.utils import celsius_to_kelvin, bar_to_pascal


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gems-cli",
        description="GEMS CLI - Thermodynamic simulation tool powered by xGEMS",
    )

    # Exploration commands
    p.add_argument("--list-systems", action="store_true",
                   help="List available pre-packaged simulation systems")
    p.add_argument("--system-info", metavar="NAME",
                   help="Show metadata for a system (elements, phases, etc.)")

    # Simulation mode
    p.add_argument("--input", "-i", metavar="FILE",
                   help="Input JSON file with simulation parameters")
    p.add_argument("--output", "-o", metavar="FILE",
                   help="Output JSON file (default: stdout)")

    # Inline parameters
    p.add_argument("--system", "-s", metavar="NAME",
                   help="Pre-packaged system name (e.g. calcite)")
    p.add_argument("--lst", metavar="FILE",
                   help="Direct path to a GEMS3K *-dat.lst file")
    p.add_argument("--T", type=float, default=None,
                   help="Temperature in Celsius")
    p.add_argument("--P", type=float, default=None,
                   help="Pressure in bar")
    p.add_argument("--T-kelvin", type=float, default=None,
                   help="Temperature in Kelvin")
    p.add_argument("--P-pascal", type=float, default=None,
                   help="Pressure in Pascal")
    p.add_argument("--T-range", metavar="TEMPS",
                   help='Comma-separated temperatures in Celsius for batch scan, e.g. "25,50,75,100"')
    p.add_argument("--bulk-composition", metavar="JSON",
                   help='Element moles as JSON string, e.g. \'{"Ca":0.01,"H":111}\'')

    # Suppress options
    p.add_argument("--suppress-species", metavar="NAMES",
                   help='Comma-separated species names to suppress, e.g. "Portlandite,Calcite"')
    p.add_argument("--suppress-phases", metavar="NAMES",
                   help='Comma-separated phase names to suppress')

    # Options
    p.add_argument("--verbose", "-v", action="store_true")

    return p


def load_input_json(path: str) -> dict:
    """Load and validate a JSON input file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "system" not in data and "lst_path" not in data:
        raise ValueError("JSON input must contain 'system' or 'lst_path' key.")
    return data


def write_output(data: dict, path: str | None = None) -> None:
    """Write JSON output to file or stdout."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    else:
        print(text)


def cmd_list_systems() -> None:
    systems = GemsExplorer.list_systems()
    if not systems:
        print("No pre-packaged systems found in data/systems/")
        return
    print("Available systems:")
    for name in systems:
        print(f"  - {name}")


def cmd_system_info(name: str) -> None:
    info = GemsExplorer.system_info(name)
    write_output(info)


def cmd_simulate(args: argparse.Namespace) -> dict:
    """Run a simulation from --input JSON or inline parameters. Returns the result dict."""

    if args.input:
        # JSON file mode
        data = load_input_json(args.input)
        system_name = data.get("system")
        lst_path = data.get("lst_path")
        conditions = data.get("conditions", {})
        T = conditions.get("T_K", celsius_to_kelvin(conditions.get("T_celsius", 25)))
        P = conditions.get("P_Pa", bar_to_pascal(conditions.get("P_bar", 1.0)))
        bulk = data.get("bulk_composition")
        suppress = data.get("suppress_species")
        suppress_phases = data.get("suppress_phases")
    else:
        # Inline mode
        system_name = args.system
        lst_path = args.lst
        if not system_name and not lst_path:
            print("Error: provide --system, --lst, or --input", file=sys.stderr)
            sys.exit(1)

        if args.T is not None:
            T = celsius_to_kelvin(args.T)
        elif args.T_kelvin is not None:
            T = args.T_kelvin
        else:
            T = 298.15

        if args.P is not None:
            P = bar_to_pascal(args.P)
        elif args.P_pascal is not None:
            P = args.P_pascal
        else:
            P = 1e5

        bulk = None
        if args.bulk_composition:
            bulk = json.loads(args.bulk_composition)
        suppress = [s.strip() for s in args.suppress_species.split(",")] if args.suppress_species else None
        suppress_phases = [s.strip() for s in args.suppress_phases.split(",")] if args.suppress_phases else None

    # Build engine
    if system_name:
        engine = GemsEngine(system_name=system_name)
    else:
        engine = GemsEngine(lst_path=lst_path)

    if args.verbose:
        print(f"System: {engine.system_name}", file=sys.stderr)
        print(f"Elements: {engine.element_names}", file=sys.stderr)

    # Run
    results = engine.equilibrate(T=T, P=P, bulk_composition=bulk,
                                 suppress_species=suppress,
                                 suppress_phases=suppress_phases)

    write_output(results, args.output)
    return results


def cmd_batch_scan(args: argparse.Namespace) -> dict:
    """Run equilibrium at multiple temperatures (batch T-scan). Returns the output dict."""
    t_range = [float(t.strip()) for t in args.T_range.split(",")]

    system_name = args.system
    lst_path = args.lst
    if not system_name and not lst_path:
        print("Error: --T-range requires --system or --lst", file=sys.stderr)
        sys.exit(1)

    P_bar = args.P if args.P is not None else 1.0

    bulk = None
    if args.bulk_composition:
        bulk = json.loads(args.bulk_composition)
    suppress = [s.strip() for s in args.suppress_species.split(",")] if args.suppress_species else None
    suppress_phases = [s.strip() for s in args.suppress_phases.split(",")] if args.suppress_phases else None

    results = []
    for t_c in t_range:
        try:
            if system_name:
                engine = GemsEngine(system_name=system_name)
            else:
                engine = GemsEngine(lst_path=lst_path)
            kwargs = {"T_celsius": t_c, "P_bar": P_bar}
            if bulk:
                kwargs["bulk_composition"] = bulk
            if suppress:
                kwargs["suppress_species"] = suppress
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

    output = {
        "system": system_name or str(lst_path),
        "P_bar": P_bar,
        "n_points": len(results),
        "results": results,
    }
    write_output(output, args.output)
    return output


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_systems:
        cmd_list_systems()
        sys.exit(0)
    elif args.system_info:
        cmd_system_info(args.system_info)
        sys.exit(0)
    elif args.T_range:
        output = cmd_batch_scan(args)
        has_errors = any(r.get("status") == "error" for r in output.get("results", []))
        sys.exit(1 if has_errors else 0)
    else:
        result = cmd_simulate(args)
        sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
