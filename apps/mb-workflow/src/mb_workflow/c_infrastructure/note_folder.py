import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import override

from pydantic import ValidationError
from safe_result import Err, Ok, Result, safe_with

from mb_workflow.b_core.c_secondary_ports.note_vault import (
    ModifiedAt,
    NoteVault,
    NoteVaultError,
    StoredNote,
    SyncState,
)
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.issue_note import NoteText, NoteTitle
from mb_workflow.d_lib.models import Model, Value


class NotePath(Value[Path]):
    @staticmethod
    def fake() -> NotePath:
        return NoteName.fake().in_folder(FolderPath.fake())


class FolderPath(Value[Path]):
    @staticmethod
    def fake() -> FolderPath:
        return FolderPath(Path("/tmp/mb-workflow-fake/vault/Linear"))


class FileText(Value[str]):
    @staticmethod
    def fake() -> FileText:
        return FileText(NoteText.fake().root)


class FileTime(Value[int]):
    @staticmethod
    def fake() -> FileTime:
        return FileTime(1_788_264_000_000_000_000)

    def modified_at(self) -> ModifiedAt:
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        return ModifiedAt(epoch + timedelta(microseconds=self.root // 1000))


# A note is named "<title> (<identifier>).md". An older sync named it "<identifier>.md", which
# still reads, without a title.
class NoteName(Model):
    issue: IssueIdentifier
    title: NoteTitle | None

    @staticmethod
    def fake() -> NoteName:
        return NoteName(issue=IssueIdentifier.fake(), title=NoteTitle.fake())

    @staticmethod
    def parsed(path: NotePath) -> NoteName | None:
        identifier = r"[A-Z][A-Z0-9]*-\d+"
        found = re.fullmatch(
            rf"(?:(?P<title>.+) \((?P<titled>{identifier})\)|(?P<bare>{identifier}))\.md",
            path.root.name,
        )
        if found is None:
            return None
        title = found.group("title")
        return NoteName(
            issue=IssueIdentifier(found.group("titled") or found.group("bare")),
            title=NoteTitle(title) if title is not None else None,
        )

    def in_folder(self, folder: FolderPath) -> NotePath:
        named = f"{self.title.root} ({self.issue.root})" if self.title else self.issue.root
        return NotePath(folder.root / f"{named}.md")


class NamedNote(Model):
    path: NotePath
    name: NoteName

    @staticmethod
    def fake() -> NamedNote:
        return NamedNote(path=NotePath.fake(), name=NoteName.fake())


# Only notes named with an identifier belong to the sync, so other notes may share the folder.
class NoteFolder(NoteVault):
    def __init__(self, folder: FolderPath) -> None:
        self._folder = folder

    @override
    def listed(self) -> Result[frozenset[IssueIdentifier], NoteVaultError]:
        match self._named(self._folder):
            case Ok(notes):
                return Ok(frozenset(note.name.issue for note in notes))
            case Err() as failed:
                return failed

    @override
    def read(self, issue: IssueIdentifier) -> Result[StoredNote | None, NoteVaultError]:
        found = self._found(self._folder, issue)
        if isinstance(found, Err):
            return found
        note = found.value
        if note is None:
            return Ok(None)

        def reading() -> StoredNote:
            return StoredNote(
                title=note.name.title,
                text=NoteText(note.path.root.read_text()),
                modified_at=FileTime(note.path.root.stat().st_mtime_ns).modified_at(),
            )

        match safe_with(OSError)(reading)():
            case Ok(stored):
                return Ok(stored)
            case Err(error):
                return Err(NoteVaultError(f"Cannot read {note.path.root}. {error}"))

    # A rename keeps the file, so Obsidian sees the note move rather than one note go and another come.
    @override
    def write(
        self, issue: IssueIdentifier, title: NoteTitle, text: NoteText
    ) -> Result[None, NoteVaultError]:
        found = self._found(self._folder, issue)
        if isinstance(found, Err):
            return found
        target = NoteName(issue=issue, title=title).in_folder(self._folder)
        if found.value is not None and found.value.path != target:
            moved = self._moved(found.value.path, target)
            if isinstance(moved, Err):
                return moved
        held = safe_with(OSError)(target.root.read_text)() if found.value is not None else None
        if isinstance(held, Ok) and held.value == text.root:
            return Ok(None)
        return self._written(target, FileText(text.root))

    @override
    def delete(self, issue: IssueIdentifier) -> Result[None, NoteVaultError]:
        found = self._found(self._folder, issue)
        if isinstance(found, Err):
            return found
        if found.value is None:
            return Ok(None)
        path = found.value.path.root
        match safe_with(OSError)(path.unlink)():
            case Ok():
                return Ok(None)
            case Err(error):
                return Err(NoteVaultError(f"Cannot delete {path}. {error}"))

    @override
    def read_state(self) -> Result[SyncState, NoteVaultError]:
        path = self._state_path().root
        if not path.is_file():
            return Ok(SyncState.empty())
        match safe_with(OSError)(path.read_text)():
            case Ok(text):
                pass
            case Err(error):
                return Err(NoteVaultError(f"Cannot read {path}. {error}"))
        match safe_with(ValidationError)(SyncState.model_validate_json)(text):
            case Ok(state):
                return Ok(state)
            case Err(error):
                return Err(NoteVaultError(f"{path} is not a valid sync state. {error}"))

    @override
    def write_state(self, state: SyncState) -> Result[None, NoteVaultError]:
        return self._written(self._state_path(), FileText(state.model_dump_json(indent=2)))

    # Written beside the file and renamed over it, so Obsidian never reads a half-written note.
    def _written(self, target: NotePath, text: FileText) -> Result[None, NoteVaultError]:
        path = target.root

        def writing() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            staged = path.with_name(f".{path.name}.tmp")
            _ = staged.write_text(text.root)
            _ = staged.replace(path)

        match safe_with(OSError)(writing)():
            case Ok():
                return Ok(None)
            case Err(error):
                return Err(NoteVaultError(f"Cannot write {path}. {error}"))

    def _moved(self, source: NotePath, target: NotePath) -> Result[None, NoteVaultError]:
        def moving() -> None:
            target.root.parent.mkdir(parents=True, exist_ok=True)
            _ = source.root.replace(target.root)

        match safe_with(OSError)(moving)():
            case Ok():
                return Ok(None)
            case Err(error):
                return Err(NoteVaultError(f"Cannot move {source.root} to {target.root}. {error}"))

    # When several notes carry the identifier, the most recently modified is kept and the rest deleted.
    def _found(
        self, folder: FolderPath, issue: IssueIdentifier
    ) -> Result[NamedNote | None, NoteVaultError]:
        named = self._named(folder)
        if isinstance(named, Err):
            return named
        matching = [note for note in named.value if note.name.issue == issue]
        if not matching:
            return Ok(None)

        def deduplicated() -> NamedNote:
            kept = matching[0]
            for note in matching[1:]:
                if note.path.root.stat().st_mtime_ns > kept.path.root.stat().st_mtime_ns:
                    kept = note
            for note in matching:
                if note != kept:
                    note.path.root.unlink()
            return kept

        match safe_with(OSError)(deduplicated)():
            case Ok(kept):
                return Ok(kept)
            case Err(error):
                return Err(NoteVaultError(f"Cannot keep one note for {issue.root}. {error}"))

    def _named(self, folder: FolderPath) -> Result[tuple[NamedNote, ...], NoteVaultError]:
        match safe_with(OSError)(lambda: tuple(folder.root.glob("*.md")))():
            case Ok(paths):
                pass
            case Err(error):
                return Err(NoteVaultError(f"Cannot list the notes in {folder.root}. {error}"))
        found = ((NotePath(path), NoteName.parsed(NotePath(path))) for path in paths)
        return Ok(
            tuple(NamedNote(path=path, name=name) for path, name in found if name is not None)
        )

    # A dotfile, so Obsidian neither lists nor indexes it.
    def _state_path(self) -> NotePath:
        return NotePath(self._folder.root / ".sync-state.json")
