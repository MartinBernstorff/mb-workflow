from datetime import UTC, date, datetime

from pydantic import NonNegativeInt

from mb_workflow.d_lib.models import Value


class Today(Value[date]):
    @staticmethod
    def fake() -> Today:
        return Today(date(2026, 9, 8))

    @staticmethod
    def now() -> Today:
        return Today(datetime.now(UTC).date())


class IntervalSeconds(Value[NonNegativeInt]):
    @staticmethod
    def fake() -> IntervalSeconds:
        return IntervalSeconds(30)
