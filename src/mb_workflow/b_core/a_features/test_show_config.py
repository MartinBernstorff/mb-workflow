from typing import TYPE_CHECKING

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.a_features.show_config import show_config
from mb_workflow.b_core.c_secondary_ports.printer import FakePrinter
from mb_workflow.b_core.d_domain_model.config import ConfigFileName, WorkingDirectory

if TYPE_CHECKING:
    from pathlib import Path


def test_reporting_a_resolved_configuration_succeeds(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "linear"\n')
    printer = FakePrinter()

    assert show_config(WorkingDirectory(tmp_path), ConfigFileName.fake(), printer) == ExitCode(0)
    assert "tracker: linear" in printer.written().root


def test_an_absent_configuration_file_fails_the_command(tmp_path: Path) -> None:
    absent = ConfigFileName("absent.toml")

    assert show_config(WorkingDirectory(tmp_path), absent, FakePrinter()) == ExitCode(1)


def test_a_malformed_configuration_file_fails_the_command(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')

    assert show_config(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), FakePrinter()
    ) == ExitCode(1)
