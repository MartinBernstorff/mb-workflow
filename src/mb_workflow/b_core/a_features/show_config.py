import logging

from mb_workflow.a_presentation.console import ExitCode
from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.c_secondary_ports.printer import PrintedText, Printer
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)

logger = logging.getLogger(__name__)


def show_config(directory: WorkingDirectory, name: ConfigFileName, printer: Printer) -> ExitCode:
    try:
        report = ConfigReport.of(Configuration.resolved(directory, name))
    except (InvalidConfigError, MissingConfigError, OSError) as error:
        logger.error("%s", error)
        return ExitCode(1)
    printer.write(PrintedText(f"{report.root}\n"))
    return ExitCode(0)
