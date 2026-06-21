"""Tests for gems_cli.cli — argparse + cmd functions."""

import json
import sys
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gems_cli.cli import (
    build_parser,
    cmd_batch_scan,
    cmd_list_systems,
    cmd_simulate,
    load_input_json,
    write_output,
)


# =============================================================================
# TestBuildParser
# =============================================================================
class TestBuildParser:
    def setup_method(self):
        self.parser = build_parser()

    def test_list_systems(self):
        args = self.parser.parse_args(["--list-systems"])
        assert args.list_systems is True

    def test_system_info(self):
        args = self.parser.parse_args(["--system-info", "calcite"])
        assert args.system_info == "calcite"

    def test_inline_args(self):
        args = self.parser.parse_args([
            "--system", "calcite", "--T", "25", "--P", "1",
        ])
        assert args.system == "calcite"
        assert args.T == 25.0
        assert args.P == 1.0

    def test_input_file(self):
        args = self.parser.parse_args(["--input", "file.json"])
        assert args.input == "file.json"

    def test_kelvin_pascal(self):
        args = self.parser.parse_args(["--T-kelvin", "373.15", "--P-pascal", "1000000"])
        assert args.T_kelvin == 373.15
        assert args.P_pascal == 1e6

    def test_suppress_options(self):
        args = self.parser.parse_args([
            "--suppress-species", "Ca+2,OH-",
            "--suppress-phases", "Calcite,Aragonite",
        ])
        assert args.suppress_species == "Ca+2,OH-"
        assert args.suppress_phases == "Calcite,Aragonite"

    def test_t_range(self):
        args = self.parser.parse_args(["--T-range", "25,50,75,100"])
        assert args.T_range == "25,50,75,100"

    def test_bulk_composition(self):
        args = self.parser.parse_args([
            "--bulk-composition", '{"Ca":0.01}',
        ])
        assert args.bulk_composition == '{"Ca":0.01}'


# =============================================================================
# TestLoadInputJson
# =============================================================================
class TestLoadInputJson:
    def test_valid_json(self, tmp_path):
        data = {"system": "calcite", "conditions": {"T_celsius": 25}}
        f = tmp_path / "input.json"
        f.write_text(json.dumps(data))
        result = load_input_json(str(f))
        assert result["system"] == "calcite"

    def test_missing_system_key(self, tmp_path):
        data = {"conditions": {"T_celsius": 25}}
        f = tmp_path / "input.json"
        f.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="system.*lst_path"):
            load_input_json(str(f))

    def test_with_lst_path(self, tmp_path):
        data = {"lst_path": "/some/path.dat.lst"}
        f = tmp_path / "input.json"
        f.write_text(json.dumps(data))
        result = load_input_json(str(f))
        assert result["lst_path"] == "/some/path.dat.lst"


# =============================================================================
# TestWriteOutput
# =============================================================================
class TestWriteOutput:
    def test_to_file(self, tmp_path):
        data = {"key": "value", "num": 42}
        out_path = tmp_path / "output.json"
        write_output(data, str(out_path))
        loaded = json.loads(out_path.read_text())
        assert loaded == data

    def test_to_stdout(self, capsys):
        data = {"key": "value"}
        write_output(data)
        captured = capsys.readouterr()
        loaded = json.loads(captured.out)
        assert loaded == data


# =============================================================================
# TestCmdFunctions
# =============================================================================
class TestCmdListSystems:
    def test_with_systems(self, capsys):
        from gems_cli.engine import GemsExplorer
        import gems_cli.cli as cli_mod
        original = GemsExplorer.list_systems
        GemsExplorer.list_systems = staticmethod(lambda: ["calcite", "iron_redox"])
        try:
            cmd_list_systems()
            output = capsys.readouterr().out
            assert "calcite" in output
            assert "iron_redox" in output
        finally:
            GemsExplorer.list_systems = original

    def test_empty(self, capsys):
        from gems_cli.engine import GemsExplorer
        original = GemsExplorer.list_systems
        GemsExplorer.list_systems = staticmethod(lambda: [])
        try:
            cmd_list_systems()
            output = capsys.readouterr().out
            assert "No pre-packaged systems found" in output
        finally:
            GemsExplorer.list_systems = original


class TestCmdSimulate:
    def test_inline_args(self, monkeypatch):
        """Test that cmd_simulate calls GemsEngine with correct T/P."""
        from gems_cli.engine import GemsEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance.equilibrate.return_value = {"status": "success"}
        mock_engine_instance.system_name = "calcite"
        mock_engine_instance.element_names = ["Ca"]
        monkeypatch.setattr(
            "gems_cli.cli.GemsEngine",
            lambda system_name=None, lst_path=None: mock_engine_instance,
        )
        args = Namespace(
            input=None, system="calcite", lst=None,
            T=25, P=1, T_kelvin=None, P_pascal=None,
            bulk_composition=None, suppress_species=None,
            suppress_phases=None, output=None, verbose=False,
        )
        cmd_simulate(args)
        mock_engine_instance.equilibrate.assert_called_once()
        call_kwargs = mock_engine_instance.equilibrate.call_args[1]
        assert call_kwargs["T"] == pytest.approx(298.15)
        assert call_kwargs["P"] == pytest.approx(1e5)


class TestCmdBatchScan:
    def test_batch_scan(self, monkeypatch, tmp_path):
        from gems_cli.engine import GemsEngine
        call_count = 0

        def mock_init(system_name=None, lst_path=None):
            nonlocal call_count
            call_count += 1
            eng = MagicMock()
            eng.equilibrate.return_value = {"status": "success"}
            return eng

        monkeypatch.setattr("gems_cli.cli.GemsEngine", mock_init)
        args = Namespace(
            T_range="25,50,75", system="calcite", lst=None,
            P=1, bulk_composition=None, suppress_species=None,
            suppress_phases=None, output=None, verbose=False,
        )
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            cmd_batch_scan(args)
        finally:
            sys.stdout = old_stdout
        assert call_count == 3


# =============================================================================
# TestExitCodes
# =============================================================================
class TestExitCodes:
    def test_simulate_success_exits_zero(self, monkeypatch):
        from gems_cli.engine import GemsEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance.equilibrate.return_value = {"status": "success"}
        mock_engine_instance.system_name = "calcite"
        mock_engine_instance.element_names = ["Ca"]
        monkeypatch.setattr(
            "gems_cli.cli.GemsEngine",
            lambda system_name=None, lst_path=None: mock_engine_instance,
        )
        args = Namespace(
            input=None, system="calcite", lst=None,
            T=25, P=1, T_kelvin=None, P_pascal=None,
            bulk_composition=None, suppress_species=None,
            suppress_phases=None, output=None, verbose=False,
        )
        result = cmd_simulate(args)
        assert result["status"] == "success"

    def test_simulate_error_exits_nonzero(self, monkeypatch):
        from gems_cli.engine import GemsEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance.equilibrate.return_value = {"status": "error", "message": "fail"}
        mock_engine_instance.system_name = "calcite"
        mock_engine_instance.element_names = ["Ca"]
        monkeypatch.setattr(
            "gems_cli.cli.GemsEngine",
            lambda system_name=None, lst_path=None: mock_engine_instance,
        )
        args = Namespace(
            input=None, system="calcite", lst=None,
            T=25, P=1, T_kelvin=None, P_pascal=None,
            bulk_composition=None, suppress_species=None,
            suppress_phases=None, output=None, verbose=False,
        )
        result = cmd_simulate(args)
        assert result["status"] == "error"

    def test_main_exits_zero_on_success(self, monkeypatch):
        from gems_cli.engine import GemsEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance.equilibrate.return_value = {"status": "success"}
        mock_engine_instance.system_name = "calcite"
        mock_engine_instance.element_names = ["Ca"]
        monkeypatch.setattr(
            "gems_cli.cli.GemsEngine",
            lambda system_name=None, lst_path=None: mock_engine_instance,
        )
        monkeypatch.setattr(
            "sys.argv",
            ["gems-cli", "--system", "calcite", "--T", "25", "--P", "1"],
        )
        from gems_cli.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_main_exits_one_on_error(self, monkeypatch):
        from gems_cli.engine import GemsEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance.equilibrate.return_value = {"status": "error", "message": "fail"}
        mock_engine_instance.system_name = "calcite"
        mock_engine_instance.element_names = ["Ca"]
        monkeypatch.setattr(
            "gems_cli.cli.GemsEngine",
            lambda system_name=None, lst_path=None: mock_engine_instance,
        )
        monkeypatch.setattr(
            "sys.argv",
            ["gems-cli", "--system", "calcite", "--T", "25", "--P", "1"],
        )
        from gems_cli.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
