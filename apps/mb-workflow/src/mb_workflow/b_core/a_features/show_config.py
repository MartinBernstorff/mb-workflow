from typing import TYPE_CHECKING

from safe_result import Err, Ok

from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    MissingConfigError,
    WorkingDirectory,
)

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.d_domain_model.config_override import ProjectOverride


def show_config(
    directory: WorkingDirectory, name: ConfigFileName, override: ProjectOverride
) -> Result[ConfigReport, InvalidConfigError | MissingConfigError]:
    match Configuration.resolved(directory, name, override):
        case Ok(config):
            return Ok(ConfigReport.of(config))
        case Err() as failed:
            return failed
