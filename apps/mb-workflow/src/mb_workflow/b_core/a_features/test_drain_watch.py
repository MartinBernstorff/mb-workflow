import logging
from typing import TYPE_CHECKING, override

import pytest
from safe_result import Err, Ok

from mb_workflow.b_core.a_features.autolabel import UnknownLabelError
from mb_workflow.b_core.a_features.drain import Changed, DrainOutcome
from mb_workflow.b_core.a_features.drain_watch import (
    DrainNarrator,
    DrainSettings,
    DrainSettingsSource,
    DrainWatch,
    WatchRequest,
)
from mb_workflow.b_core.a_features.test_drain import (
    fake_board,
    fake_manager,
    in_progress,
    opened_issues,
    pool_of,
    pool_with_total,
    pooled,
    standard_pool,
)
from mb_workflow.b_core.c_secondary_ports.claims import FakeClaimRegistry
from mb_workflow.b_core.c_secondary_ports.run_lock import FakeRunLock
from mb_workflow.b_core.c_secondary_ports.stop_signal import FakeStopSignal, Stopped, WaitCount
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
    FakeTicketTracker,
    TicketTrackerError,
)
from mb_workflow.b_core.c_secondary_ports.tie_break import ReversingTieBreak
from mb_workflow.b_core.d_domain_model.config import InvalidConfigError, PoolSettings
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName, LabelNames
from mb_workflow.b_core.d_domain_model.pool import Limit, PoolTickets, Priority

if TYPE_CHECKING:
    from safe_result import Result

    from mb_workflow.b_core.c_secondary_ports.claims import UnknownClaimLabelError
    from mb_workflow.b_core.c_secondary_ports.workspace_manager import FakeWorkspaceManager
    from mb_workflow.b_core.d_domain_model.pool import ViewSlug


# Serves each settings in turn, then keeps serving the last.
class SequencedSettings(DrainSettingsSource):
    def __init__(self, *pools: PoolSettings) -> None:
        self._pools = list(pools)

    @override
    def current(self) -> DrainSettings:
        pool = self._pools.pop(0) if len(self._pools) > 1 else self._pools[0]
        return DrainSettings.fake().model_copy(update={"pool": pool})


class MissingPoolSettings(DrainSettingsSource):
    @override
    def current(self) -> DrainSettings:
        raise InvalidConfigError("Set [pool] view")


class RecordingNarrator(DrainNarrator):
    def __init__(self) -> None:
        self.passes: list[tuple[DrainOutcome, Changed]] = []

    @override
    def passed(self, outcome: DrainOutcome, changed: Changed) -> None:
        self.passes.append((outcome, changed))


# Fails the next listing of the view, as if the tracker were briefly unreachable.
class FlakyTracker(FakeTicketTracker):
    failing = False

    def fail_next_listing(self) -> None:
        self.failing = True

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]:
        if self.failing:
            self.failing = False
            return Err(TicketTrackerError("Linear is unreachable"))
        return super().unblocked_view_tickets(view)


# Requests a stop while listing the view, as if Ctrl-C arrived mid-pass.
class SignallingTracker(FakeTicketTracker):
    stop: FakeStopSignal | None = None

    def signal_on_listing(self, stop: FakeStopSignal) -> None:
        self.stop = stop

    @override
    def unblocked_view_tickets(self, view: ViewSlug) -> Result[PoolTickets, TicketTrackerError]:
        if self.stop is not None:
            self.stop.signal()
        return super().unblocked_view_tickets(view)


def watching(
    tracker: FakeTicketTracker,
    stop: FakeStopSignal,
    *,
    manager: FakeWorkspaceManager | None = None,
    lock: FakeRunLock | None = None,
    settings: DrainSettingsSource | None = None,
    narrator: RecordingNarrator | None = None,
) -> Result[None, UnknownClaimLabelError | UnknownLabelError]:
    return DrainWatch.watch_pool(
        tracker=tracker,
        claims=FakeClaimRegistry(),
        manager=manager or fake_manager(),
        board=fake_board(),
        lock=lock or FakeRunLock(),
        tie_break=ReversingTieBreak(),
        flow_labels=FlowLabels.fake(),
        settings=settings or SequencedSettings(PoolSettings.fake()),
        stop=stop,
        narrator=narrator or RecordingNarrator(),
        request=WatchRequest.fake(),
    )


def test_runs_passes_until_the_stop_signal() -> None:
    passes = WaitCount(3)
    narrator = RecordingNarrator()
    stop = FakeStopSignal(passes)
    assert watching(standard_pool(), stop, narrator=narrator) == Ok(None)
    assert stop.requested() == Stopped(True)
    assert len(narrator.passes) == passes.root


def test_a_stop_requested_before_the_first_pass_runs_none() -> None:
    narrator = RecordingNarrator()
    stop = FakeStopSignal()
    stop.signal()
    assert watching(standard_pool(), stop, narrator=narrator) == Ok(None)
    assert narrator.passes == []


def test_a_stop_during_a_pass_lets_the_pass_finish_then_ends_the_watch() -> None:
    manager = fake_manager()
    stop = FakeStopSignal()
    tracker = standard_pool(SignallingTracker)
    assert isinstance(tracker, SignallingTracker)
    tracker.signal_on_listing(stop)
    started = (IssueIdentifier("MB-2"), IssueIdentifier("MB-1"))
    assert watching(tracker, stop, manager=manager) == Ok(None)
    assert opened_issues(manager) == started
    assert stop.waits() == WaitCount(0)


def test_a_raised_limit_applies_from_the_next_pass() -> None:
    manager = fake_manager()
    settings = SequencedSettings(pool_with_total(Limit(1)), pool_with_total(Limit(2)))
    started = (IssueIdentifier("MB-2"), IssueIdentifier("MB-1"))
    assert watching(
        standard_pool(), FakeStopSignal(WaitCount(2)), manager=manager, settings=settings
    ) == Ok(None)
    assert opened_issues(manager) == started


def test_a_pass_skips_while_another_drain_holds_the_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    lock = FakeRunLock()
    manager = fake_manager()
    passes = WaitCount(2)
    stop = FakeStopSignal(passes)
    skipped = "Skipped this pass"
    with caplog.at_level(logging.INFO), lock.acquire().unwrap():
        assert watching(standard_pool(), stop, manager=manager, lock=lock) == Ok(None)
    assert opened_issues(manager) == ()
    assert stop.waits() == passes
    assert caplog.text.count(skipped) == passes.root


def test_a_tracker_failure_is_retried_on_the_next_pass() -> None:
    manager = fake_manager()
    tracker = standard_pool(FlakyTracker)
    assert isinstance(tracker, FlakyTracker)
    tracker.fail_next_listing()
    started = (IssueIdentifier("MB-2"), IssueIdentifier("MB-1"))
    assert watching(tracker, FakeStopSignal(WaitCount(2)), manager=manager) == Ok(None)
    assert opened_issues(manager) == started


def test_a_pass_refused_over_conflicting_flow_labels_is_retried_on_the_next_pass() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        elsewhere=(
            in_progress(
                IssueIdentifier("MB-10"),
                StateName("Grilling"),
                labels=LabelNames((LabelName("QA"),)),
            ),
        ),
    )
    narrator = RecordingNarrator()
    passes = WaitCount(2)
    stop = FakeStopSignal(passes)
    assert watching(tracker, stop, narrator=narrator) == Ok(None)
    assert narrator.passes == []
    assert stop.waits() == passes


def test_an_unknown_label_ends_the_watch() -> None:
    tracker = pool_of(
        pooled(IssueIdentifier("MB-1"), Priority.low),
        labels=LabelNames((LabelName("claimed"), *FlowLabels.fake().labels.root)),
    )
    stop = FakeStopSignal(WaitCount(3))
    ended = watching(tracker, stop)
    assert isinstance(ended, Err)
    assert isinstance(ended.error, UnknownLabelError)
    assert stop.waits() == WaitCount(0)


def test_a_config_without_a_pool_ends_the_watch() -> None:
    stop = FakeStopSignal(WaitCount(3))
    with pytest.raises(InvalidConfigError):
        _ = watching(standard_pool(), stop, settings=MissingPoolSettings())
    assert stop.waits() == WaitCount(0)


def test_only_passes_that_differ_from_the_last_count_as_changed() -> None:
    narrator = RecordingNarrator()
    assert watching(standard_pool(), FakeStopSignal(WaitCount(3)), narrator=narrator) == Ok(None)
    assert tuple(changed for _, changed in narrator.passes) == (
        Changed(True),
        Changed(True),
        Changed(False),
    )
