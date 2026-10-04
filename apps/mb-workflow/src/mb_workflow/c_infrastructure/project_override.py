import tomllib
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.d_domain_model.config_override import (
    InvalidOverrideError,
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    ProjectOverride,
    SettingsTable,
)
from mb_workflow.c_infrastructure.credentials import (
    CredentialsDirectory,
    CredentialTables,
    NoOriginError,
    RepositorySlug,
)

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.shell import CommandRunner


@safe_with(OSError, tomllib.TOMLDecodeError)
def parsed_override(path: OverridePath) -> SettingsTable:
    return SettingsTable(tomllib.loads(path.root.read_text()))


def override_at(path: OverridePath) -> Result[ProjectOverride, InvalidOverrideError]:
    if not path.root.exists():
        return Ok(NoOverrideFile(expected=path))
    match parsed_override(path):
        case Ok(table):
            credential_tables = CredentialTables.of_credentials().root
            settings = SettingsTable(
                {key: value for key, value in table.root.items() if key not in credential_tables}
            )
            return Ok(OverrideFile(path=path, table=settings))
        case Err(error):
            return Err(InvalidOverrideError(f"Cannot read the override file {path.root}. {error}"))


def override_of_origin(
    directory: CredentialsDirectory, runner: CommandRunner
) -> Result[ProjectOverride, InvalidOverrideError]:
    match RepositorySlug.of_origin(runner):
        case Ok(repository):
            return override_at(OverridePath(directory.path_for(repository).root))
        case Err(NoOriginError()):
            return Ok(NoOverrideFile(expected=None))
        case Err(error):
            return Err(InvalidOverrideError(str(error)))
