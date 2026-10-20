from enum import StrEnum
from operator import attrgetter
from typing import TYPE_CHECKING

from safe_result import Err, Ok, Result

from mb_workflow.b_core.c_secondary_ports.note_vault import Freshness, NoteHash, SyncRecord
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, IssueUpdate
from mb_workflow.b_core.d_domain_model.issue_note import IssueNote, NoteTitle
from mb_workflow.b_core.d_domain_model.outcome import Failed
from mb_workflow.d_lib.models import Model, Value

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.note_vault import (
        NoteVault,
        NoteVaultError,
        StoredNote,
        SyncState,
    )
    from mb_workflow.b_core.c_secondary_ports.ticket_tracker import (
        TicketTracker,
        TicketTrackerError,
    )
    from mb_workflow.b_core.d_domain_model.issue import IssueSnapshot, IssueSnapshots, UpdatedAt
    from mb_workflow.b_core.d_domain_model.pool import ViewSlug


class SyncOutcome(StrEnum):
    created = "created"
    pulled = "pulled"
    pushed = "pushed"
    unchanged = "unchanged"
    archived = "archived"
    failed = "failed"


class SyncFailure(Value[str]):
    @staticmethod
    def fake() -> SyncFailure:
        return SyncFailure("No status is named Doing.")


class NoteSync(Model):
    issue: IssueIdentifier
    outcome: SyncOutcome
    failure: SyncFailure | None = None

    @staticmethod
    def fake() -> NoteSync:
        return NoteSync(issue=IssueIdentifier.fake(), outcome=SyncOutcome.pulled)


class VaultSyncReport(Value[tuple[NoteSync, ...]]):
    @staticmethod
    def fake() -> VaultSyncReport:
        return VaultSyncReport((NoteSync.fake(),))

    def failed(self) -> Failed:
        return Failed(any(sync.outcome == SyncOutcome.failed for sync in self.root))

    def outcome_of(self, issue: IssueIdentifier) -> SyncOutcome | None:
        return next((sync.outcome for sync in self.root if sync.issue == issue), None)


class Direction(StrEnum):
    none = "none"
    pull = "pull"
    push = "push"


# The vault's state holds, per issue, the note's hash and the issue's update time at the last sync,
# so a run tells which side changed without stamping anything into the notes. When both changed,
# the later writer wins. A note is only written when its text changes, so Obsidian does not reload it
# for nothing.
class VaultSync:
    def __init__(self, tracker: TicketTracker, vault: NoteVault, state: SyncState) -> None:
        self._tracker = tracker
        self._vault = vault
        self._state = state

    @staticmethod
    def sync_view(
        tracker: TicketTracker, vault: NoteVault, view: ViewSlug
    ) -> Result[VaultSyncReport, TicketTrackerError | NoteVaultError]:
        snapshots = tracker.view_snapshots(view)
        if isinstance(snapshots, Err):
            return snapshots
        state = vault.read_state()
        if isinstance(state, Err):
            return state
        run = VaultSync(tracker, vault, state.value)
        report = run._report(snapshots.value)
        # Saved even when the run stops early, so the notes it did write are known to be in step.
        saved = vault.write_state(run._state)
        if isinstance(saved, Err):
            return saved
        return report

    def _report(self, snapshots: IssueSnapshots) -> Result[VaultSyncReport, NoteVaultError]:
        synced: list[NoteSync] = []
        for snapshot in snapshots.root:
            note = self._synced(snapshot)
            if isinstance(note, Err):
                return note
            synced.append(note.value)
        listed = self._vault.listed()
        if isinstance(listed, Err):
            return listed
        for issue in sorted(listed.value - snapshots.identifiers(), key=attrgetter("root")):
            departed = self._departed(issue)
            if isinstance(departed, Err):
                return departed
            synced.extend(departed.value)
        return Ok(VaultSyncReport(tuple(synced)))

    # A failure confined to one issue is reported for that issue, so the others still sync.
    def _synced(self, snapshot: IssueSnapshot) -> Result[NoteSync, NoteVaultError]:
        stored = self._stored(snapshot.identifier())
        if isinstance(stored, Err):
            return stored
        if stored.value is None:
            return self._pulled(snapshot, None, SyncOutcome.created)
        match self._direction(snapshot.identifier(), stored.value, snapshot.updated_at):
            case Direction.none:
                # A note named by an older sync, without a title, takes its title from the issue.
                if stored.value.title is None:
                    return self._pulled(snapshot, stored.value, SyncOutcome.pulled)
                return Ok(NoteSync(issue=snapshot.identifier(), outcome=SyncOutcome.unchanged))
            case Direction.pull:
                changed = NoteHash.of(
                    NoteTitle.of(snapshot.detail.title), IssueNote.rendered(snapshot)
                ) != NoteHash.of(stored.value.title, stored.value.text)
                outcome = SyncOutcome.pulled if changed else SyncOutcome.unchanged
                return self._pulled(snapshot, stored.value, outcome)
            case Direction.push:
                return self._pushed(snapshot, stored.value)

    # A note without a record, as on the first run, is compared by its modification time.
    def _direction(
        self, issue: IssueIdentifier, stored: StoredNote, updated_at: UpdatedAt
    ) -> Direction:
        record = self._state.record_of(issue)
        note_changed = record is None or NoteHash.of(stored.title, stored.text) != record.note_hash
        issue_changed = record is None or updated_at != record.issue_updated_at
        if note_changed and issue_changed:
            newer = stored.modified_at.against(updated_at) == Freshness.note_newer
            return Direction.push if newer else Direction.pull
        if note_changed:
            return Direction.push
        if issue_changed:
            return Direction.pull
        return Direction.none

    # A note edited before its issue left the view is pushed before it is archived, so the edit
    # reaches Linear. If the push fails, the note stays in place to be fixed.
    def _departed(self, issue: IssueIdentifier) -> Result[tuple[NoteSync, ...], NoteVaultError]:
        stored = self._vault.read(issue)
        if isinstance(stored, Err):
            return stored
        record = self._state.record_of(issue)
        pushed: tuple[NoteSync, ...] = ()
        if stored.value is not None and (
            record is None or NoteHash.of(stored.value.title, stored.value.text) != record.note_hash
        ):
            match self._tracker.read_snapshot(issue):
                case Ok(snapshot):
                    pass
                case Err(error):
                    return Ok((VaultSync._failed(issue, error).unwrap(),))
            if self._direction(issue, stored.value, snapshot.updated_at) == Direction.push:
                sync = self._pushed(snapshot, stored.value)
                if isinstance(sync, Err):
                    return sync
                if sync.value.outcome == SyncOutcome.failed:
                    return Ok((sync.value,))
                pushed = (sync.value,)
        archived = self._vault.archive(issue)
        if isinstance(archived, Err):
            return archived
        return Ok((*pushed, NoteSync(issue=issue, outcome=SyncOutcome.archived)))

    # A note archived while its issue was out of the view comes back when the issue returns.
    def _stored(self, issue: IssueIdentifier) -> Result[StoredNote | None, NoteVaultError]:
        stored = self._vault.read(issue)
        if isinstance(stored, Err) or stored.value is not None:
            return stored
        restored = self._vault.restore(issue)
        if isinstance(restored, Err):
            return restored
        return self._vault.read(issue) if restored.value.root else Ok(None)

    def _pushed(
        self, snapshot: IssueSnapshot, stored: StoredNote
    ) -> Result[NoteSync, NoteVaultError]:
        issue = snapshot.identifier()
        match IssueNote.parsed(stored.text):
            case Ok(note):
                pass
            case Err(error):
                return VaultSync._failed(issue, error)
        update = note.update_of(snapshot.detail, stored.title)
        # Edits to fields Linear owns change nothing, so the note is rewritten from the issue.
        if update == IssueUpdate.nothing():
            return self._pulled(snapshot, stored, SyncOutcome.unchanged)
        updated = self._tracker.update_issue(issue, update)
        if isinstance(updated, Err):
            return VaultSync._failed(issue, updated.error)
        match self._tracker.read_snapshot(issue):
            case Ok(fresh):
                return self._pulled(fresh, stored, SyncOutcome.pushed)
            case Err(error):
                return VaultSync._failed(issue, error)

    # Writes the note only when the issue renders differently from it, and records both as in step.
    # A note whose title alone differs is renamed, not rewritten.
    def _pulled(
        self, snapshot: IssueSnapshot, stored: StoredNote | None, outcome: SyncOutcome
    ) -> Result[NoteSync, NoteVaultError]:
        issue = snapshot.identifier()
        title = NoteTitle.of(snapshot.detail.title)
        rendered = IssueNote.rendered(snapshot)
        if stored is None or (stored.title, stored.text) != (title, rendered):
            written = self._vault.write(issue, title, rendered)
            if isinstance(written, Err):
                return written
        self._state = self._state.with_record(
            SyncRecord(
                issue=issue,
                issue_updated_at=snapshot.updated_at,
                note_hash=NoteHash.of(title, rendered),
            )
        )
        return Ok(NoteSync(issue=issue, outcome=outcome))

    @staticmethod
    def _failed(issue: IssueIdentifier, error: Exception) -> Result[NoteSync, NoteVaultError]:
        return Ok(
            NoteSync(issue=issue, outcome=SyncOutcome.failed, failure=SyncFailure(str(error)))
        )
