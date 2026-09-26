from pathlib import Path

from pydantic import model_validator

from mb_workflow.d_lib.models import Value


class ExistingDirectory(Value[Path]):
    @model_validator(mode="after")
    def directory_exists(self) -> ExistingDirectory:
        if not self.root.is_dir():
            raise ValueError(f"Not a directory: {self.root}")
        return self

    @staticmethod
    def fake() -> ExistingDirectory:
        return ExistingDirectory(Path.cwd())
