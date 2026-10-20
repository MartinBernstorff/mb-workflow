from datetime import timedelta

from assertions import Assert

from mb_workflow.b_core.a_features.sync_vault import SyncOutcome, VaultSync, VaultSyncReport
from mb_workflow.b_core.c_secondary_ports.note_vault import (
    FakeNoteVault,
    ModifiedAt,
    NoteHash,
    NoteWrites,
    StoredNote,
    SyncRecord,
    SyncState,
)
from mb_workflow.b_core.c_secondary_ports.ticket_tracker import FakeTicketTracker, TrackedIssue
from mb_workflow.b_core.d_domain_model.issue import (
    Issue,
    IssueIdentifier,
    IssueSnapshot,
    IssueStatusName,
    IssueTitle,
    LabelNames,
    UpdatedAt,
)
from mb_workflow.b_core.d_domain_model.issue_note import IssueNote, NoteText, NoteTitle
from mb_workflow.b_core.d_domain_model.pool import ViewSlug
from mb_workflow.d_lib.models import Value


class Fragment(Value[str]):
    @staticmethod
    def fake() -> Fragment:
        return Fragment("title: Add widget")


def tracking(*issues: TrackedIssue) -> FakeTicketTracker:
    return FakeTicketTracker(
        LabelNames.fake(),
        issues,
        views={ViewSlug.fake(): tuple(tracked.issue.identifier for tracked in issues)},
    )


def other_issue(identifier: IssueIdentifier) -> TrackedIssue:
    return TrackedIssue.fake().model_copy(
        update={"issue": Issue.fake().model_copy(update={"identifier": identifier})}
    )


def snapshot_of(tracker: FakeTicketTracker, issue: IssueIdentifier) -> IssueSnapshot:
    return tracker.read_snapshot(issue).unwrap()


def in_step(tracker: FakeTicketTracker, issue: IssueIdentifier) -> StoredNote:
    snapshot = snapshot_of(tracker, issue)
    return StoredNote(
        title=NoteTitle.of(snapshot.detail.title),
        text=IssueNote.rendered(snapshot),
        modified_at=ModifiedAt.fake(),
    )


def later() -> ModifiedAt:
    return ModifiedAt(UpdatedAt.fake().root + timedelta(minutes=1))


def earlier() -> ModifiedAt:
    return ModifiedAt(UpdatedAt.fake().root - timedelta(minutes=1))


def edited(note: StoredNote, held: Fragment, replacement: Fragment, at: ModifiedAt) -> StoredNote:
    Assert.that(note.text.root).contains(held.root)
    return note.model_copy(
        update={
            "text": NoteText(note.text.root.replace(held.root, replacement.root, 1)),
            "modified_at": at,
        }
    )


def retitled(note: StoredNote, title: IssueTitle, at: ModifiedAt) -> StoredNote:
    return note.model_copy(update={"title": NoteTitle(title.root), "modified_at": at})


# The record a sync leaves when the note was named and held this, and the issue had this update time.
def recorded(issue: IssueIdentifier, note: StoredNote, updated_at: UpdatedAt) -> SyncState:
    return SyncState(
        (
            SyncRecord(
                issue=issue,
                issue_updated_at=updated_at,
                note_hash=NoteHash.of(note.title, note.text),
            ),
        )
    )


def note_of(vault: FakeNoteVault, issue: IssueIdentifier) -> StoredNote:
    return Assert.that(vault.read(issue).unwrap()).is_instance(StoredNote)


def synced(tracker: FakeTicketTracker, vault: FakeNoteVault) -> VaultSyncReport:
    return VaultSync.sync_view(tracker, vault, ViewSlug.fake()).unwrap()


def an_hour_before(updated_at: UpdatedAt) -> UpdatedAt:
    return UpdatedAt(updated_at.root - timedelta(hours=1))


def test_an_issue_without_a_note_gets_one() -> None:
    tracker = tracking(TrackedIssue.fake())
    vault = FakeNoteVault()
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.created)
    Assert.that(vault.read(IssueIdentifier.fake()).unwrap()).matches(
        in_step(tracker, IssueIdentifier.fake())
    )


def test_a_note_and_issue_unchanged_since_the_last_sync_are_left_alone() -> None:
    tracker = tracking(TrackedIssue.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): note},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.unchanged)
    Assert.that(vault.writes()).matches(NoteWrites(0))


def test_an_issue_updated_since_the_last_sync_overwrites_the_note() -> None:
    tracker = tracking(TrackedIssue.fake())
    stale = retitled(in_step(tracker, IssueIdentifier.fake()), IssueTitle("Old title"), later())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): stale},
        state=recorded(IssueIdentifier.fake(), stale, an_hour_before(UpdatedAt.fake())),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pulled)
    Assert.that(note_of(vault, IssueIdentifier.fake()).title).matches(
        in_step(tracker, IssueIdentifier.fake()).title
    )


def test_an_issue_updated_where_the_note_does_not_show_leaves_the_note_unwritten() -> None:
    tracker = tracking(TrackedIssue.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): note},
        state=recorded(IssueIdentifier.fake(), note, an_hour_before(UpdatedAt.fake())),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.unchanged)
    Assert.that(vault.writes()).matches(NoteWrites(0))


def test_an_issue_retitled_in_linear_renames_the_note_without_rewriting_it() -> None:
    tracker = tracking(TrackedIssue.fake())
    current = in_step(tracker, IssueIdentifier.fake())
    stale = retitled(current, IssueTitle("Old title"), earlier())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): stale},
        state=recorded(IssueIdentifier.fake(), stale, an_hour_before(UpdatedAt.fake())),
    )
    _ = synced(tracker, vault)
    Assert.that(note_of(vault, IssueIdentifier.fake()).title).matches(current.title)
    Assert.that(vault.writes()).matches(NoteWrites(0))


def test_a_note_named_by_an_older_sync_is_renamed_with_its_title() -> None:
    tracker = tracking(TrackedIssue.fake())
    current = in_step(tracker, IssueIdentifier.fake())
    untitled = current.model_copy(update={"title": None})
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): untitled},
        state=recorded(IssueIdentifier.fake(), untitled, UpdatedAt.fake()),
    )
    _ = synced(tracker, vault)
    Assert.that(note_of(vault, IssueIdentifier.fake()).title).matches(current.title)


def test_a_note_edited_since_the_last_sync_updates_the_issue() -> None:
    tracker = tracking(TrackedIssue.fake())
    title = IssueTitle("Add a better widget")
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): retitled(note, title, earlier())},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pushed)
    Assert.that(tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().title).matches(title)


def test_a_pushed_note_that_matches_the_issue_is_not_rewritten() -> None:
    tracker = tracking(TrackedIssue.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): retitled(note, IssueTitle("Renamed"), later())},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    _ = synced(tracker, vault)
    Assert.that(vault.writes()).matches(NoteWrites(0))


def test_a_note_pushed_and_left_alone_is_unchanged_on_the_next_run() -> None:
    tracker = tracking(TrackedIssue.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): retitled(note, IssueTitle("Renamed"), later())},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    _ = synced(tracker, vault)
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.unchanged)


def test_when_both_changed_a_note_edited_later_wins() -> None:
    tracker = tracking(TrackedIssue.fake())
    title = IssueTitle("Edited after the issue")
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): retitled(note, title, later())},
        state=recorded(IssueIdentifier.fake(), note, an_hour_before(UpdatedAt.fake())),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pushed)
    Assert.that(tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().title).matches(title)


def test_when_both_changed_an_issue_updated_later_wins() -> None:
    tracker = tracking(TrackedIssue.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): retitled(note, IssueTitle("Edited before the issue"), earlier())},
        state=recorded(IssueIdentifier.fake(), note, an_hour_before(UpdatedAt.fake())),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pulled)
    Assert.that(note_of(vault, IssueIdentifier.fake()).title).matches(note.title)


def test_a_note_without_a_record_is_compared_by_its_modification_time() -> None:
    tracker = tracking(TrackedIssue.fake())
    title = IssueTitle("Edited before the first sync")
    note = retitled(in_step(tracker, IssueIdentifier.fake()), title, later())
    vault = FakeNoteVault({IssueIdentifier.fake(): note})
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pushed)
    Assert.that(tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().title).matches(title)


def test_a_note_edited_only_where_linear_owns_the_field_leaves_the_issue_alone() -> None:
    tracker = tracking(TrackedIssue.fake())
    before = snapshot_of(tracker, IssueIdentifier.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        {
            IssueIdentifier.fake(): edited(
                note, Fragment("url: https"), Fragment("url: http"), later()
            )
        },
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.unchanged)
    Assert.that(snapshot_of(tracker, IssueIdentifier.fake())).matches(before)
    Assert.that(note_of(vault, IssueIdentifier.fake()).text).matches(note.text)


def test_an_unreadable_note_fails_alone_and_the_other_issues_still_sync() -> None:
    other = IssueIdentifier("E-2")
    tracker = tracking(TrackedIssue.fake(), other_issue(other))
    broken = StoredNote(
        title=NoteTitle.fake(), text=NoteText("no frontmatter"), modified_at=later()
    )
    vault = FakeNoteVault({IssueIdentifier.fake(): broken})
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.failed)
    Assert.that(report.outcome_of(other)).matches(SyncOutcome.created)
    Assert.that(report.failed().root).is_true()
    Assert.that(vault.read(IssueIdentifier.fake()).unwrap()).matches(broken)


def test_a_note_that_failed_to_push_is_tried_again_on_the_next_run() -> None:
    tracker = tracking(TrackedIssue.fake())
    before = snapshot_of(tracker, IssueIdentifier.fake())
    note = in_step(tracker, IssueIdentifier.fake())
    unknown = edited(
        note,
        Fragment(f"status: {IssueStatusName.fake().root}"),
        Fragment("status: Doing"),
        later(),
    )
    vault = FakeNoteVault(
        {IssueIdentifier.fake(): unknown},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    _ = synced(tracker, vault)
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.failed)
    Assert.that(snapshot_of(tracker, IssueIdentifier.fake())).matches(before)
    Assert.that(vault.read(IssueIdentifier.fake()).unwrap()).matches(unknown)


def test_the_note_of_an_issue_that_left_the_view_is_archived() -> None:
    gone = IssueIdentifier("E-2")
    tracker = tracking(TrackedIssue.fake(), other_issue(gone))
    vault = FakeNoteVault()
    _ = synced(tracker, vault)
    tracker.set_view(ViewSlug.fake(), (IssueIdentifier.fake(),))
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(gone)).matches(SyncOutcome.archived)
    Assert.that(vault.archived()).matches(frozenset({gone}))
    Assert.that(vault.listed().unwrap()).matches(frozenset({IssueIdentifier.fake()}))


def test_a_note_edited_before_its_issue_left_the_view_is_pushed_then_archived() -> None:
    gone = IssueIdentifier("E-2")
    tracker = tracking(TrackedIssue.fake(), other_issue(gone))
    title = IssueTitle("Edited before leaving")
    note = in_step(tracker, gone)
    vault = FakeNoteVault(
        {gone: retitled(note, title, later())}, state=recorded(gone, note, UpdatedAt.fake())
    )
    tracker.set_view(ViewSlug.fake(), (IssueIdentifier.fake(),))
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(gone)).matches(SyncOutcome.pushed)
    Assert.that(tracker.read_issue_detail(gone).unwrap().title).matches(title)
    Assert.that(vault.archived()).matches(frozenset({gone}))


def test_a_note_that_fails_to_push_as_its_issue_leaves_the_view_stays_in_place() -> None:
    gone = IssueIdentifier("E-2")
    tracker = tracking(TrackedIssue.fake(), other_issue(gone))
    note = in_step(tracker, gone)
    unknown = edited(
        note,
        Fragment(f"status: {IssueStatusName.fake().root}"),
        Fragment("status: Doing"),
        later(),
    )
    vault = FakeNoteVault({gone: unknown}, state=recorded(gone, note, UpdatedAt.fake()))
    tracker.set_view(ViewSlug.fake(), (IssueIdentifier.fake(),))
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(gone)).matches(SyncOutcome.failed)
    Assert.that(vault.archived()).matches(frozenset())
    Assert.that(vault.read(gone).unwrap()).matches(unknown)


def test_an_archived_note_returns_with_its_issue_and_keeps_its_edits() -> None:
    tracker = tracking(TrackedIssue.fake())
    title = IssueTitle("Edited while archived")
    note = in_step(tracker, IssueIdentifier.fake())
    vault = FakeNoteVault(
        archived={IssueIdentifier.fake(): retitled(note, title, later())},
        state=recorded(IssueIdentifier.fake(), note, UpdatedAt.fake()),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pushed)
    Assert.that(vault.archived()).matches(frozenset())
    Assert.that(tracker.read_issue_detail(IssueIdentifier.fake()).unwrap().title).matches(title)


def test_an_archived_note_returns_updated_when_its_issue_changed_while_away() -> None:
    tracker = tracking(TrackedIssue.fake())
    stale = retitled(in_step(tracker, IssueIdentifier.fake()), IssueTitle("Old title"), earlier())
    vault = FakeNoteVault(
        archived={IssueIdentifier.fake(): stale},
        state=recorded(IssueIdentifier.fake(), stale, an_hour_before(UpdatedAt.fake())),
    )
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.pulled)
    Assert.that(note_of(vault, IssueIdentifier.fake()).title).matches(
        in_step(tracker, IssueIdentifier.fake()).title
    )


def test_a_deleted_note_is_recreated() -> None:
    tracker = tracking(TrackedIssue.fake())
    vault = FakeNoteVault()
    _ = synced(tracker, vault)
    vault = FakeNoteVault(state=vault.read_state().unwrap())
    report = synced(tracker, vault)
    Assert.that(report.outcome_of(IssueIdentifier.fake())).matches(SyncOutcome.created)
    Assert.that(vault.read(IssueIdentifier.fake()).unwrap()).matches(
        in_step(tracker, IssueIdentifier.fake())
    )
