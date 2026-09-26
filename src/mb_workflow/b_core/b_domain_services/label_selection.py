from mb_workflow.b_core.d_domain_model.autolabel import AutoLabelCriteria, SkipReason
from mb_workflow.b_core.d_domain_model.issue import Issue, Issues
from mb_workflow.d_lib.models import Model, Value


class SkipCount(Value[int]):
    @staticmethod
    def fake() -> SkipCount:
        return SkipCount(1)


class Decision(Model):
    issue: Issue
    skipped: SkipReason | None

    @staticmethod
    def fake() -> Decision:
        return Decision(issue=Issue.fake(), skipped=None)


class SkipTally(Model):
    reason: SkipReason
    count: SkipCount

    @staticmethod
    def fake() -> SkipTally:
        return SkipTally(reason=SkipReason.already_labelled, count=SkipCount.fake())


class Selection(Value[tuple[Decision, ...]]):
    @staticmethod
    def fake() -> Selection:
        return Selection((Decision.fake(),))

    @staticmethod
    def of(issues: Issues, criteria: AutoLabelCriteria) -> Selection:
        return Selection(
            tuple(Decision(issue=issue, skipped=criteria.skipped(issue)) for issue in issues.root)
        )

    def labellable(self) -> Issues:
        return Issues(tuple(decision.issue for decision in self.root if decision.skipped is None))

    def skips(self) -> tuple[SkipTally, ...]:
        counts = {
            reason: sum(1 for decision in self.root if decision.skipped == reason)
            for reason in SkipReason
        }
        return tuple(
            SkipTally(reason=reason, count=SkipCount(count))
            for reason, count in counts.items()
            if count > 0
        )
