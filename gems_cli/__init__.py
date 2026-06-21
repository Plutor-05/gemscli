"""gems_cli - CLI tool wrapping xGEMS for AI Agent thermodynamic simulation."""

__version__ = "0.1.0"


def check_xgems():
    """Import and return ChemicalEngineDicts, or raise with installation instructions."""
    try:
        from xgems import ChemicalEngineDicts
        return ChemicalEngineDicts
    except ImportError:
        raise ImportError(
            "xgems is required but not installed. Install via:\n"
            "  conda config --add channels conda-forge\n"
            "  conda install xgems\n"
            "xgems is not available on PyPI."
        )


def check_xgems_lowlevel():
    """Import and return ChemicalEngine, or raise with installation instructions."""
    try:
        from xgems import ChemicalEngine
        return ChemicalEngine
    except ImportError:
        raise ImportError(
            "xgems is required but not installed. Install via:\n"
            "  conda config --add channels conda-forge\n"
            "  conda install xgems\n"
            "xgems is not available on PyPI."
        )
