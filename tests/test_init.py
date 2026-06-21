"""Tests for gems_cli.__init__ — check_xgems import gate."""

import builtins
import sys
import types

import pytest


class TestCheckXgems:
    def test_success(self, monkeypatch):
        """When xgems is importable, returns ChemicalEngineDicts."""
        mock_module = types.ModuleType("xgems")

        class FakeEngine:
            pass

        mock_module.ChemicalEngineDicts = FakeEngine
        monkeypatch.setitem(sys.modules, "xgems", mock_module)

        from gems_cli import check_xgems
        result = check_xgems()
        assert result is FakeEngine

    def test_import_error(self, monkeypatch):
        """When xgems not installed, raises ImportError with install instructions."""
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "xgems":
                raise ImportError("No module named 'xgems'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from gems_cli import check_xgems
        with pytest.raises(ImportError, match="conda install xgems"):
            check_xgems()
