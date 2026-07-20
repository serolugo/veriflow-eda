"""Regression tests for the 10 critical UX error-handling fixes.

Groups:
  A — FileNotFoundError -> VeriFlowError (wrap init, wrap generate, rtl sources, tile int)
  B — yaml.YAMLError    -> VeriFlowError (project_config, wrap config, db tile/project, create-tile)
  C — wrap wizard non-interactive guard
  D — wrap wizard cancel returns 0 with message
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from veriflow.core import VeriFlowError


# ── shared fixtures ───────────────────────────────────────────────────────────

_DUT_V = """\
module my_dut (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [15:0] data_i,
    output wire  [7:0] result_o
);
endmodule
"""

_VALID_CONFIG = {
    "interface_name": "semicolab",
    "metadata": {"name": "my_dut"},
    "design": {
        "top_module": "my_dut",
        "rtl_sources": ["my_dut.v"],
    },
    "ports": {
        "clk_i": "clk",
        "rst_ni": "arst_n",
        "data_i": "csr_in[15:0]",
        "result_o": "csr_out[7:0]",
    },
}

_MALFORMED_YAML = "key: [unclosed bracket\n  bad: yaml\n"


@pytest.fixture
def dut_dir(tmp_path: Path) -> Path:
    (tmp_path / "my_dut.v").write_text(_DUT_V, encoding="utf-8")
    return tmp_path


@pytest.fixture
def valid_config_file(dut_dir: Path) -> Path:
    p = dut_dir / "wrapper_config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG), encoding="utf-8")
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP A — FileNotFoundError -> VeriFlowError
# ═══════════════════════════════════════════════════════════════════════════════

class TestWrapInitRtlNotFound:
    """api.wrap_init: --top with non-existent file -> VF_WRAP_RTL_FILE_NOT_FOUND."""

    def test_raises_veriflow_error_not_file_not_found(self, tmp_path):
        from veriflow.api import wrap_init
        missing = tmp_path / "ghost.v"
        with pytest.raises(VeriFlowError):
            wrap_init("semicolab", missing)

    def test_error_code(self, tmp_path):
        from veriflow.api import wrap_init
        missing = tmp_path / "ghost.v"
        with pytest.raises(VeriFlowError) as exc_info:
            wrap_init("semicolab", missing)
        assert exc_info.value.code == "VF_WRAP_RTL_FILE_NOT_FOUND"

    def test_error_message_contains_path(self, tmp_path):
        from veriflow.api import wrap_init
        missing = tmp_path / "ghost.v"
        with pytest.raises(VeriFlowError) as exc_info:
            wrap_init("semicolab", missing)
        assert "ghost.v" in str(exc_info.value)

    def test_details_contains_path(self, tmp_path):
        from veriflow.api import wrap_init
        missing = tmp_path / "ghost.v"
        with pytest.raises(VeriFlowError) as exc_info:
            wrap_init("semicolab", missing)
        assert exc_info.value.details is not None
        assert "path" in exc_info.value.details

    def test_not_file_not_found_exception(self, tmp_path):
        from veriflow.api import wrap_init
        missing = tmp_path / "ghost.v"
        with pytest.raises(VeriFlowError):
            wrap_init("semicolab", missing)
        # The outer except must be VeriFlowError, not FileNotFoundError
        try:
            wrap_init("semicolab", missing)
        except VeriFlowError:
            pass
        except FileNotFoundError:
            pytest.fail("FileNotFoundError leaked through -- fix not applied")


class TestWrapGenerateConfigNotFound:
    """WrapWorkflow.generate: config file missing -> VF_WRAP_CONFIG_NOT_FOUND."""

    def test_raises_veriflow_error(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        missing = tmp_path / "no_config.yaml"
        with pytest.raises(VeriFlowError):
            WrapWorkflow().generate(missing)

    def test_error_code(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        missing = tmp_path / "no_config.yaml"
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(missing)
        assert exc_info.value.code == "VF_WRAP_CONFIG_NOT_FOUND"

    def test_error_message_contains_path(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        missing = tmp_path / "no_config.yaml"
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(missing)
        assert "no_config.yaml" in str(exc_info.value)

    def test_not_file_not_found_exception(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        missing = tmp_path / "no_config.yaml"
        try:
            WrapWorkflow().generate(missing)
        except VeriFlowError:
            pass
        except FileNotFoundError:
            pytest.fail("FileNotFoundError leaked through -- fix not applied")


class TestWrapGenerateRtlSourceNotFound:
    """WrapWorkflow.generate: rtl_sources path missing -> VF_WRAP_RTL_SOURCE_NOT_FOUND."""

    def _config_with_missing_rtl(self, directory: Path) -> Path:
        cfg = dict(_VALID_CONFIG)
        cfg["design"] = {"top_module": "my_dut", "rtl_sources": ["ghost.v"]}
        p = directory / "wrapper_config.yaml"
        p.write_text(yaml.dump(cfg), encoding="utf-8")
        return p

    def test_raises_veriflow_error(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        config = self._config_with_missing_rtl(tmp_path)
        with pytest.raises(VeriFlowError):
            WrapWorkflow().generate(config)

    def test_error_code(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        config = self._config_with_missing_rtl(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(config)
        assert exc_info.value.code == "VF_WRAP_RTL_SOURCE_NOT_FOUND"

    def test_error_message_contains_missing_file(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        config = self._config_with_missing_rtl(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(config)
        assert "ghost.v" in str(exc_info.value)

    def test_details_contain_path(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        config = self._config_with_missing_rtl(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(config)
        assert exc_info.value.details is not None
        assert "path" in exc_info.value.details

    def test_not_file_not_found_exception(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        config = self._config_with_missing_rtl(tmp_path)
        try:
            WrapWorkflow().generate(config)
        except VeriFlowError:
            pass
        except FileNotFoundError:
            pytest.fail("FileNotFoundError leaked through -- fix not applied")


class TestTileNumberInvalid:
    """db waves / bump-version / bump-revision: non-numeric --tile -> VF_TILE_NUMBER_INVALID."""

    def _make_db(self, tmp_path: Path) -> Path:
        from veriflow.commands.init_db import cmd_init
        db = tmp_path / "db"
        cmd_init(db)
        return db

    def test_waves_non_numeric_raises_veriflow_error(self, tmp_path):
        from veriflow.commands.waves import cmd_waves
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError):
            cmd_waves(db, tile_number="abc")

    def test_waves_non_numeric_error_code(self, tmp_path):
        from veriflow.commands.waves import cmd_waves
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_waves(db, tile_number="abc")
        assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"

    def test_waves_non_numeric_not_value_error(self, tmp_path):
        from veriflow.commands.waves import cmd_waves
        db = self._make_db(tmp_path)
        try:
            cmd_waves(db, tile_number="abc")
        except VeriFlowError:
            pass
        except ValueError:
            pytest.fail("ValueError leaked through -- fix not applied")

    def test_bump_version_non_numeric_raises_veriflow_error(self, tmp_path):
        from veriflow.commands.bump_version import cmd_bump_version
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError):
            cmd_bump_version(db, tile_number="xyz")

    def test_bump_version_non_numeric_error_code(self, tmp_path):
        from veriflow.commands.bump_version import cmd_bump_version
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_bump_version(db, tile_number="xyz")
        assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"

    def test_bump_revision_non_numeric_raises_veriflow_error(self, tmp_path):
        from veriflow.commands.bump_revision import cmd_bump_revision
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError):
            cmd_bump_revision(db, tile_number="xyz")

    def test_bump_revision_non_numeric_error_code(self, tmp_path):
        from veriflow.commands.bump_revision import cmd_bump_revision
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_bump_revision(db, tile_number="xyz")
        assert exc_info.value.code == "VF_TILE_NUMBER_INVALID"

    def test_error_message_contains_bad_value(self, tmp_path):
        from veriflow.commands.waves import cmd_waves
        db = self._make_db(tmp_path)
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_waves(db, tile_number="bad_tile")
        assert "bad_tile" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP B — yaml.YAMLError -> VeriFlowError
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectConfigYamlError:
    """ProjectWorkflowConfig.from_file: malformed YAML -> VF_PROJECT_CONFIG_YAML_ERROR."""

    def test_raises_veriflow_error_not_yaml_error(self, tmp_path):
        from veriflow.workflows.project_config import ProjectWorkflowConfig
        bad = tmp_path / "veriflow.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError):
            ProjectWorkflowConfig.from_file(bad)

    def test_error_code(self, tmp_path):
        from veriflow.workflows.project_config import ProjectWorkflowConfig
        bad = tmp_path / "veriflow.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            ProjectWorkflowConfig.from_file(bad)
        assert exc_info.value.code == "VF_PROJECT_CONFIG_YAML_ERROR"

    def test_error_message_contains_path(self, tmp_path):
        from veriflow.workflows.project_config import ProjectWorkflowConfig
        bad = tmp_path / "veriflow.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            ProjectWorkflowConfig.from_file(bad)
        assert "veriflow.yaml" in str(exc_info.value)

    def test_not_yaml_error_exception(self, tmp_path):
        from veriflow.workflows.project_config import ProjectWorkflowConfig
        bad = tmp_path / "veriflow.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        try:
            ProjectWorkflowConfig.from_file(bad)
        except VeriFlowError:
            pass
        except yaml.YAMLError:
            pytest.fail("yaml.YAMLError leaked through -- fix not applied")


class TestWrapConfigYamlError:
    """WrapWorkflow.generate: malformed wrapper_config.yaml -> VF_WRAP_CONFIG_YAML_ERROR."""

    def test_raises_veriflow_error(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        bad = tmp_path / "wrapper_config.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError):
            WrapWorkflow().generate(bad)

    def test_error_code(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        bad = tmp_path / "wrapper_config.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(bad)
        assert exc_info.value.code == "VF_WRAP_CONFIG_YAML_ERROR"

    def test_error_message_contains_path(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        bad = tmp_path / "wrapper_config.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            WrapWorkflow().generate(bad)
        assert "wrapper_config.yaml" in str(exc_info.value)

    def test_not_yaml_error_exception(self, tmp_path):
        from veriflow.workflows.wrap import WrapWorkflow
        bad = tmp_path / "wrapper_config.yaml"
        bad.write_text(_MALFORMED_YAML, encoding="utf-8")
        try:
            WrapWorkflow().generate(bad)
        except VeriFlowError:
            pass
        except yaml.YAMLError:
            pytest.fail("yaml.YAMLError leaked through -- fix not applied")


class TestDatabaseTileConfigYamlError:
    """DatabaseWorkflow.run_tile: malformed tile_config.yaml -> VF_TILE_CONFIG_YAML_ERROR.

    VF_TILE_CONFIG_YAML_ERROR (not VF_DATABASE_CONFIG_YAML_ERROR) since
    dev-docs/MODE_CONSISTENCY_AUDIT.md's Finding 4 fix: each YAML-parse-error
    code now corresponds unambiguously to one file -- VF_TILE_CONFIG_YAML_ERROR
    for tile_config.yaml, VF_DATABASE_CONFIG_YAML_ERROR for project_config.yaml
    (see TestDatabaseProjectConfigYamlError / TestCreateTileProjectConfigYamlError
    below, both of which parse project_config.yaml and both now use
    VF_DATABASE_CONFIG_YAML_ERROR)."""

    def _make_db_with_tile(self, tmp_path: Path):
        from veriflow.commands.init_db import cmd_init
        from veriflow.commands.create_tile import cmd_create_tile
        db = tmp_path / "db"
        cmd_init(db)
        # Set a minimal project config to avoid VF_PROJECT_INTERFACE_REQUIRED
        (db / "project_config.yaml").write_text(
            "id_prefix: TST\nproject_name: T\nrepo: r\ndescription: d\ninterface_name: null\n",
            encoding="utf-8",
        )
        cmd_create_tile(db)
        return db

    def test_tile_config_malformed_yaml_raises_veriflow_error(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        tile_cfg = db / "config" / "tile_0001" / "tile_config.yaml"
        tile_cfg.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError):
            DatabaseWorkflow(db).run_tile("0001")

    def test_tile_config_malformed_yaml_error_code(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        tile_cfg = db / "config" / "tile_0001" / "tile_config.yaml"
        tile_cfg.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            DatabaseWorkflow(db).run_tile("0001")
        assert exc_info.value.code == "VF_TILE_CONFIG_YAML_ERROR"

    def test_tile_config_malformed_yaml_message_contains_path(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        tile_cfg = db / "config" / "tile_0001" / "tile_config.yaml"
        tile_cfg.write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            DatabaseWorkflow(db).run_tile("0001")
        assert "tile_config.yaml" in str(exc_info.value)

    def test_tile_config_not_yaml_error_exception(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        tile_cfg = db / "config" / "tile_0001" / "tile_config.yaml"
        tile_cfg.write_text(_MALFORMED_YAML, encoding="utf-8")
        try:
            DatabaseWorkflow(db).run_tile("0001")
        except VeriFlowError:
            pass
        except yaml.YAMLError:
            pytest.fail("yaml.YAMLError leaked through -- fix not applied")


class TestDatabaseProjectConfigYamlError:
    """DatabaseWorkflow.run_tile: malformed project_config.yaml -> VF_DATABASE_CONFIG_YAML_ERROR."""

    def _make_db_with_tile(self, tmp_path: Path):
        from veriflow.commands.init_db import cmd_init
        from veriflow.commands.create_tile import cmd_create_tile
        db = tmp_path / "db"
        cmd_init(db)
        (db / "project_config.yaml").write_text(
            "id_prefix: TST\nproject_name: T\nrepo: r\ndescription: d\ninterface_name: null\n",
            encoding="utf-8",
        )
        cmd_create_tile(db)
        return db

    def test_project_config_malformed_yaml_raises_veriflow_error(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError):
            DatabaseWorkflow(db).run_tile("0001")

    def test_project_config_malformed_yaml_error_code(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            DatabaseWorkflow(db).run_tile("0001")
        assert exc_info.value.code == "VF_DATABASE_CONFIG_YAML_ERROR"

    def test_project_config_malformed_yaml_message_contains_path(self, tmp_path):
        from veriflow.workflows.database import DatabaseWorkflow
        db = self._make_db_with_tile(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            DatabaseWorkflow(db).run_tile("0001")
        assert "project_config.yaml" in str(exc_info.value)


class TestCreateTileProjectConfigYamlError:
    """cmd_create_tile: malformed project_config.yaml -> VF_DATABASE_CONFIG_YAML_ERROR.

    VF_DATABASE_CONFIG_YAML_ERROR (not VF_TILE_CONFIG_YAML_ERROR -- this
    file is project_config.yaml, not tile_config.yaml) since
    dev-docs/MODE_CONSISTENCY_AUDIT.md's Finding 4 fix: create_tile.py's own
    project_config.yaml parse now uses the same code
    workflows/database.py's project_config.yaml parse already used
    (TestDatabaseProjectConfigYamlError above) -- previously it used
    VF_TILE_CONFIG_YAML_ERROR by mistake, a misleading duplicate."""

    def _make_db(self, tmp_path: Path) -> Path:
        from veriflow.commands.init_db import cmd_init
        db = tmp_path / "db"
        cmd_init(db)
        return db

    def test_malformed_raises_veriflow_error(self, tmp_path):
        from veriflow.commands.create_tile import cmd_create_tile
        db = self._make_db(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError):
            cmd_create_tile(db)

    def test_malformed_error_code(self, tmp_path):
        from veriflow.commands.create_tile import cmd_create_tile
        db = self._make_db(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_create_tile(db)
        assert exc_info.value.code == "VF_DATABASE_CONFIG_YAML_ERROR"

    def test_malformed_message_contains_path(self, tmp_path):
        from veriflow.commands.create_tile import cmd_create_tile
        db = self._make_db(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        with pytest.raises(VeriFlowError) as exc_info:
            cmd_create_tile(db)
        assert "project_config.yaml" in str(exc_info.value)

    def test_not_yaml_error_exception(self, tmp_path):
        from veriflow.commands.create_tile import cmd_create_tile
        db = self._make_db(tmp_path)
        (db / "project_config.yaml").write_text(_MALFORMED_YAML, encoding="utf-8")
        try:
            cmd_create_tile(db)
        except VeriFlowError:
            pass
        except yaml.YAMLError:
            pytest.fail("yaml.YAMLError leaked through -- fix not applied")


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP C — wrap wizard non-interactive guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestWrapWizardNonInteractive:
    """CLI: wrap wizard with --non-interactive -> VF_WIZARD_NOT_INTERACTIVE (exit 2)."""

    def test_non_interactive_raises_veriflow_error(self):
        from veriflow.cli import main
        rc = main(["--non-interactive", "wrap", "wizard"])
        assert rc == 2

    def test_non_interactive_exit_code_2(self):
        from veriflow.cli import main
        rc = main(["--non-interactive", "wrap", "wizard"])
        assert rc == 2

    def test_non_interactive_json_mode_error_code(self, capsys):
        from veriflow.cli import main
        rc = main(["--non-interactive", "--json", "wrap", "wizard"])
        assert rc == 2
        import json
        out = json.loads(capsys.readouterr().out)
        assert out["error"]["code"] == "VF_WIZARD_NOT_INTERACTIVE"

    def test_non_interactive_clean_stderr_message(self, capsys):
        from veriflow.cli import main
        main(["--non-interactive", "wrap", "wizard"])
        captured = capsys.readouterr()
        assert "interactive" in captured.err.lower()
        assert "Traceback" not in captured.err

    def test_interactive_mode_still_dispatches(self, monkeypatch):
        """Without --non-interactive the wizard is reached (EOFError from input is fine)."""
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
        from veriflow.cli import main
        # In text mode the CLI re-raises unhandled exceptions; EOFError signals dispatch occurred.
        # We just verify the guard code (VF_WIZARD_NOT_INTERACTIVE) is NOT what fires.
        with pytest.raises(EOFError):
            main(["wrap", "wizard"])


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP D — wrap wizard cancel returns 0 with message
# ═══════════════════════════════════════════════════════════════════════════════

class TestWrapWizardCancel:
    """wrap wizard: cancelling in the re-map loop returns 0 and prints message.

    The re-map loop is triggered by making validate_mapping return FAIL on its
    final call. Since cancel_dut has one port (clk) and the user leaves it
    unmapped (Enter), no per-port validate_mapping calls occur — only the final
    call runs, so we can safely make ALL calls return FAIL.
    """

    _DUT_V_CANCEL = """\
module cancel_dut (
    input wire clk
);
endmodule
"""

    @pytest.fixture
    def cancel_dut_dir(self, tmp_path: Path) -> Path:
        (tmp_path / "cancel_dut.v").write_text(self._DUT_V_CANCEL, encoding="utf-8")
        return tmp_path

    def _build_fail_result(self):
        from veriflow.core.wrapper.validator import WrapValidationResult
        return WrapValidationResult(
            status="FAIL",
            mapped=[],
            unmapped_ip_ports=["clk"],
            unmapped_interface_ports=[],
            errors=[{"code": "VF_TEST_FORCED", "message": "forced fail for cancel test", "severity": "error"}],
            info=[],
        )

    def _run_wizard_to_cancel(self, cancel_dut_dir, tmp_path, monkeypatch):
        """Drive the wizard to the re-map cancel prompt and press Enter to cancel.

        validate_mapping is patched on the source module so the local import
        inside cmd_wrap_wizard picks up the mock at call time.
        """
        import veriflow.core.wrapper.validator as _validator_mod

        # Patch validate_mapping at module level — the wizard imports it locally
        # from this module, so it will receive our mock when it runs.
        monkeypatch.setattr(_validator_mod, "validate_mapping", lambda *a, **kw: self._build_fail_result())

        responses = iter([
            "1",                                    # interface: semicolab
            "cancel_dut",                           # top module
            str(cancel_dut_dir / "cancel_dut.v"),  # rtl source
            "",                                     # end rtl sources
            "",                                     # clk: unmapped (skips per-port validation)
            "",                                     # re-map loop: Enter to cancel
        ])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))

        from veriflow.commands.wrap_wizard import cmd_wrap_wizard
        args = argparse.Namespace(force=False)
        return cmd_wrap_wizard(args)

    def test_cancel_returns_exit_code_0(self, cancel_dut_dir, tmp_path, monkeypatch):
        rc = self._run_wizard_to_cancel(cancel_dut_dir, tmp_path, monkeypatch)
        assert rc == 0

    def test_cancel_prints_cancelled_message(self, cancel_dut_dir, tmp_path, monkeypatch, capsys):
        self._run_wizard_to_cancel(cancel_dut_dir, tmp_path, monkeypatch)
        captured = capsys.readouterr()
        assert "cancelled" in captured.err.lower()

    def test_cancel_no_files_written(self, cancel_dut_dir, tmp_path, monkeypatch):
        self._run_wizard_to_cancel(cancel_dut_dir, tmp_path, monkeypatch)
        assert not (tmp_path / "wrapper_config.yaml").exists()
