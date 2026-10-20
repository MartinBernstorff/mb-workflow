import os
from typing import TYPE_CHECKING

from assertions import Assert

from mb_workflow.b_core.c_secondary_ports.note_vault import Restored, StoredNote, SyncState
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.issue_note import NoteText, NoteTitle
from mb_workflow.c_infrastructure.note_folder import FolderPath, NoteFolder

if TYPE_CHECKING:
    from pathlib import Path


def stored(folder: NoteFolder) -> StoredNote:
    return Assert.that(folder.read(IssueIdentifier.fake()).unwrap()).is_instance(StoredNote)


def test_a_written_note_is_named_by_its_title_and_identifier(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write(IssueIdentifier.fake(), NoteTitle.fake(), NoteText.fake()).unwrap()
    expected = f"{NoteTitle.fake().root} ({IssueIdentifier.fake().root}).md"
    Assert.that((tmp_path / expected).is_file()).is_true()


def test_a_written_note_reads_back(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write(IssueIdentifier.fake(), NoteTitle.fake(), NoteText.fake()).unwrap()
    Assert.that((stored(folder).title, stored(folder).text)).matches(
        (NoteTitle.fake(), NoteText.fake())
    )


def test_a_retitled_note_is_renamed_and_keeps_its_file(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write(IssueIdentifier.fake(), NoteTitle.fake(), NoteText.fake()).unwrap()
    before = stored(folder)
    title = NoteTitle("Add a better widget")
    folder.write(IssueIdentifier.fake(), title, NoteText.fake()).unwrap()
    Assert.that(stored(folder)).matches(before.model_copy(update={"title": title}))
    Assert.that(len(tuple(tmp_path.glob("*.md")))).matches(1)


def test_a_note_named_by_its_identifier_alone_reads_without_a_title(tmp_path: Path) -> None:
    _ = (tmp_path / f"{IssueIdentifier.fake().root}.md").write_text(NoteText.fake().root)
    Assert.that(stored(NoteFolder(FolderPath(tmp_path))).title).matches(None)


def test_of_two_notes_for_one_issue_the_later_is_kept_and_the_other_deleted(
    tmp_path: Path,
) -> None:
    older = tmp_path / f"Old title ({IssueIdentifier.fake().root}).md"
    newer = tmp_path / f"{NoteTitle.fake().root} ({IssueIdentifier.fake().root}).md"
    _ = older.write_text("older")
    _ = newer.write_text(NoteText.fake().root)
    os.utime(older, (0, 0))
    Assert.that(stored(NoteFolder(FolderPath(tmp_path))).title).matches(NoteTitle.fake())
    Assert.that(older.exists()).is_false()


def test_a_missing_note_reads_as_none(tmp_path: Path) -> None:
    Assert.that(NoteFolder(FolderPath(tmp_path)).read(IssueIdentifier.fake()).unwrap()).matches(
        None
    )


def test_only_notes_named_with_an_identifier_are_listed(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write(IssueIdentifier.fake(), NoteTitle.fake(), NoteText.fake()).unwrap()
    folder.write_state(SyncState.fake()).unwrap()
    _ = (tmp_path / "Index.md").write_text("Notes on the board")
    Assert.that(folder.listed().unwrap()).matches(frozenset({IssueIdentifier.fake()}))


def test_an_archived_note_is_restored_with_its_name_and_modification_time(
    tmp_path: Path,
) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write(IssueIdentifier.fake(), NoteTitle.fake(), NoteText.fake()).unwrap()
    written = stored(folder)
    folder.archive(IssueIdentifier.fake()).unwrap()
    Assert.that(folder.listed().unwrap()).matches(frozenset())
    Assert.that(folder.restore(IssueIdentifier.fake()).unwrap()).matches(Restored(True))
    Assert.that(stored(folder)).matches(written)


def test_restoring_a_note_never_archived_restores_nothing(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    Assert.that(folder.restore(IssueIdentifier.fake()).unwrap()).matches(Restored(False))


def test_a_written_state_reads_back(tmp_path: Path) -> None:
    folder = NoteFolder(FolderPath(tmp_path))
    folder.write_state(SyncState.fake()).unwrap()
    Assert.that(folder.read_state().unwrap()).matches(SyncState.fake())


def test_a_folder_never_synced_has_an_empty_state(tmp_path: Path) -> None:
    Assert.that(NoteFolder(FolderPath(tmp_path)).read_state().unwrap()).matches(SyncState.empty())
