from typing import TYPE_CHECKING

from mb_workflow.b_core.d_domain_model.config import (
    ConfigExistsError,
    ConfigFileName,
    ConfigPath,
    SearchedDirectories,
    WorkingDirectory,
)
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.config_template import ConfigTemplate


class Overwrite(Value[bool]):
    @staticmethod
    def fake() -> Overwrite:
        return Overwrite(False)


class InitOutcome(Model):
    written: ConfigPath
    shadowed: ConfigPath | None

    @staticmethod
    def fake() -> InitOutcome:
        return InitOutcome(written=ConfigPath.fake(), shadowed=None)


def init_config(
    directory: WorkingDirectory,
    name: ConfigFileName,
    template: ConfigTemplate,
    overwrite: Overwrite,
) -> InitOutcome:
    target = directory.root.resolve() / name.root
    if target.exists() and not overwrite.root:
        raise ConfigExistsError(f"{target} already exists. Pass --force to overwrite it.")
    _ = target.write_text(template.root)
    return InitOutcome(
        written=ConfigPath(target), shadowed=SearchedDirectories.above(directory).find(name)
    )
