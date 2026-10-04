from hemolint.b_core.d_domain_model.violation import ReportedViolation
from hemolint.d_lib.models import Value


class UnparsableLineError(Exception):
    pass


class LinterOutput(Value[str]):
    @staticmethod
    def fake() -> LinterOutput:
        return LinterOutput("src/app.py@1:3 CompareSingletonPrimitivesByIs: Use `is`.\n")


class ReportedViolations(Value[tuple[ReportedViolation, ...]]):
    @staticmethod
    def fake() -> ReportedViolations:
        return ReportedViolations((ReportedViolation.fake(),))
