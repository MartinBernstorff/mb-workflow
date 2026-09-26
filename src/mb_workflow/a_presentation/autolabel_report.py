import logging

from mb_workflow.b_core.a_features.autolabel import Outcome
from mb_workflow.b_core.d_domain_model.autolabel import SkipCount, SkipReason
from mb_workflow.d_lib.models import Value

logger = logging.getLogger(__name__)


class SkipPhrase(Value[str]):
    @staticmethod
    def fake() -> SkipPhrase:
        return skip_phrase(SkipReason.already_labelled, SkipCount.fake())


class SummaryLine(Value[str]):
    @staticmethod
    def fake() -> SummaryLine:
        return outcome_summary(Outcome.fake())


def skip_phrase(reason: SkipReason, count: SkipCount) -> SkipPhrase:
    if count.root == 1:
        return SkipPhrase(f"{count.root} {reason.value}")
    plural = {
        SkipReason.excluded_status: "excluded statuses",
        SkipReason.excluded_project: "excluded projects",
    }.get(reason, reason.value)
    return SkipPhrase(f"{count.root} {plural}")


def outcome_summary(outcome: Outcome) -> SummaryLine:
    chosen = outcome.chosen()
    verb = "Would label" if outcome.dry_run.root else "Labelled"
    total = len(outcome.selection.root)
    parts = [f"{verb} {len(chosen)} of {total} issue{'' if total == 1 else 's'}"]
    skips = outcome.selection.skips()
    if len(skips) > 0:
        parts.append("skipped " + ", ".join(skip_phrase(t.reason, t.count).root for t in skips))
    if len(outcome.failed) > 0:
        parts.append(f"{len(outcome.failed)} failed")
    return SummaryLine("; ".join(parts))


def log_outcome(outcome: Outcome) -> None:
    verb = "would label" if outcome.dry_run.root else "labelled"
    for issue in outcome.chosen():
        logger.info("%s %s", verb, issue.root)
    logger.info("%s", outcome_summary(outcome).root)
    if outcome.dry_run.root:
        logger.info("Re-run with --apply to label them.")
