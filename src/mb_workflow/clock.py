from datetime import UTC, date, datetime

from mb_workflow.models import Value


class Today(Value[date]):
    @staticmethod
    def fake() -> Today:
        return Today(date(2026, 9, 8))

    @staticmethod
    def now() -> Today:
        return Today(datetime.now(UTC).date())
