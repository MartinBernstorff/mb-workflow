import sys
from typing import TYPE_CHECKING

from mb_workflow.d_lib.models import Value

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.outcome import Failed


class ExitCode(Value[int]):
    @staticmethod
    def fake() -> ExitCode:
        return ExitCode(0)

    @staticmethod
    def of(failed: Failed) -> ExitCode:
        return ExitCode(1 if failed.root else 0)


class Output(Value[str]):
    @staticmethod
    def fake() -> Output:
        return Output("Grilling\n")


def write(output: Output) -> None:
    _ = sys.stdout.write(output.root)
