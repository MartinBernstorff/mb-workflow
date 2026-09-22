from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    Configuration,
    WorkingDirectory,
)


def show_config(directory: WorkingDirectory, name: ConfigFileName) -> ConfigReport:
    return ConfigReport.of(Configuration.resolved(directory, name))
