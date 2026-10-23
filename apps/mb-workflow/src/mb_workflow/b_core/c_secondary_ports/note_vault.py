import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Protocol, override

from safe_result import Ok, Result

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, UpdatedAt
from mb_workflow.b_core.d_domain_model.issue_note import NoteText, NoteTitle
from mb_workflow.d_lib.models import Model, Value


class NoteVaultError(Exception):
    pass


class Freshness(StrEnum):
    in_step = "in step"
    note_newer = "note newer"
    issue_newer = "issue newer"


class ModifiedAt(Value[datetime]):
    @staticmethod
    def fake() -> ModifiedAt:
        return ModifiedAt(UpdatedAt.fake().root)

    def against(self, updated: UpdatedAt) -> Freshness:
        if self.root == updated.root:
            return Freshness.in_step
        if self.root > updated.root:
            return Freshness.note_newer
        return Freshness.issue_newer


# A note named by its identifier alone, as an older sync named it, has no title.
class StoredNote(Model):
    title: NoteTitle | None
    text: NoteText
    modified_at: ModifiedAt

    @staticmethod
    def fake() -> StoredNote:
        return StoredNote(
            title=NoteTitle.fake(), text=NoteText.fake(), modified_at=ModifiedAt.fake()
        )


class NoteHash(Value[str]):
    @staticmethod
    def fake() -> NoteHash:
        return NoteHash.of(NoteTitle.fake(), NoteText.fake())

    @staticmethod
    def of(title: NoteTitle | None, text: NoteText) -> NoteHash:
        named = title.root if title is not None else ""
        return NoteHash(hashlib.sha256(f"{named}\n{text.root}".encode()).hexdigest())


# What a note and its issue were when they were last in step, so the next run can tell which changed.
class SyncRecord(Model):
    issue: IssueIdentifier
    issue_updated_at: UpdatedAt
    note_hash: NoteHash

    @staticmethod
    def fake() -> SyncRecord:
        return SyncRecord(
            issue=IssueIdentifier.fake(),
            issue_updated_at=UpdatedAt.fake(),
            note_hash=NoteHash.fake(),
        )


class SyncState(Value[tuple[SyncRecord, ...]]):
    @staticmethod
    def fake() -> SyncState:
        return SyncState((SyncRecord.fake(),))

    @staticmethod
    def empty() -> SyncState:
        return SyncState(())

    def record_of(self, issue: IssueIdentifier) -> SyncRecord | None:
        return next((record for record in self.root if record.issue == issue), None)

    def with_record(self, record: SyncRecord) -> SyncState:
        kept = tuple(held for held in self.root if held.issue != record.issue)
        return SyncState((*kept, record))


# A folder of notes named by title and issue identifier, with the state of the last sync kept beside
# the notes.
class NoteVault(Protocol):
    def listed(self) -> Result[frozenset[IssueIdentifier], NoteVaultError]: ...

    def read(self, issue: IssueIdentifier) -> Result[StoredNote | None, NoteVaultError]: ...

    # Renames the note when its title changed, and rewrites it only when its text changed.
    def write(
        self, issue: IssueIdentifier, title: NoteTitle, text: NoteText
    ) -> Result[None, NoteVaultError]: ...

    def delete(self, issue: IssueIdentifier) -> Result[None, NoteVaultError]: ...

    # A vault never synced has an empty state.
    def read_state(self) -> Result[SyncState, NoteVaultError]: ...

    def write_state(self, state: SyncState) -> Result[None, NoteVaultError]: ...


class NoteWrites(Value[int]):
    @staticmethod
    def fake() -> NoteWrites:
        return NoteWrites(1)


class FakeNoteVault(NoteVault):
    def __init__(
        self,
        notes: dict[IssueIdentifier, StoredNote] | None = None,
        state: SyncState | None = None,
        now: ModifiedAt | None = None,
    ) -> None:
        self._notes = dict(notes or {})
        self._state = state or SyncState.empty()
        self._now = now or ModifiedAt.fake()
        self._writes = 0

    def writes(self) -> NoteWrites:
        return NoteWrites(self._writes)

    @override
    def listed(self) -> Result[frozenset[IssueIdentifier], NoteVaultError]:
        return Ok(frozenset(self._notes))

    @override
    def read(self, issue: IssueIdentifier) -> Result[StoredNote | None, NoteVaultError]:
        return Ok(self._notes.get(issue))

    @override
    def write(
        self, issue: IssueIdentifier, title: NoteTitle, text: NoteText
    ) -> Result[None, NoteVaultError]:
        held = self._notes.get(issue)
        if held is not None and held.text == text:
            self._notes[issue] = held.model_copy(update={"title": title})
            return Ok(None)
        self._notes[issue] = StoredNote(title=title, text=text, modified_at=self._now)
        self._writes += 1
        return Ok(None)

    @override
    def delete(self, issue: IssueIdentifier) -> Result[None, NoteVaultError]:
        _ = self._notes.pop(issue, None)
        return Ok(None)

    @override
    def read_state(self) -> Result[SyncState, NoteVaultError]:
        return Ok(self._state)

    @override
    def write_state(self, state: SyncState) -> Result[None, NoteVaultError]:
        self._state = state
        return Ok(None)
