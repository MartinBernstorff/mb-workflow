from assertions import Assert

from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    Cleared,
    IssueDescription,
    IssueDetail,
    IssueIdentifier,
    IssueSnapshot,
    IssueStatusName,
    IssueTitle,
    IssueUpdate,
    LabelName,
    LabelNames,
    Priority,
)
from mb_workflow.b_core.d_domain_model.issue_note import (
    InvalidNoteError,
    IssueNote,
    NoteText,
    NoteTitle,
)
from mb_workflow.d_lib.models import Value


class Fragment(Value[str]):
    @staticmethod
    def fake() -> Fragment:
        return Fragment("priority: medium")


def edited(text: NoteText, held: Fragment, replacement: Fragment) -> NoteText:
    Assert.that(text.root).contains(held.root)
    return NoteText(text.root.replace(held.root, replacement.root, 1))


def update_of(text: NoteText) -> IssueUpdate:
    return (
        Assert.that(IssueNote.parsed(text))
        .is_ok()
        .update_of(IssueSnapshot.fake().detail, NoteTitle.fake())
    )


def test_a_rendered_note_reads_back_as_no_change() -> None:
    Assert.that(update_of(IssueNote.rendered(IssueSnapshot.fake()))).matches(IssueUpdate.nothing())


def test_a_rendered_note_leaves_out_the_issues_it_relates_to() -> None:
    blocker = IssueIdentifier("E-1")
    detail = IssueDetail.fake().model_copy(
        update={"blocked_by": frozenset({blocker}), "parent": blocker}
    )
    snapshot = IssueSnapshot.fake().model_copy(update={"detail": detail})
    Assert.that(blocker.root in IssueNote.rendered(snapshot).root).is_false()


def test_a_wiki_link_escaped_by_linear_reads_as_a_link_and_as_no_change() -> None:
    link = Fragment("[[AdPlacementFormat]]")
    escaped = IssueDescription("Every ad has one \\[\\[AdPlacementFormat\\]\\].")
    detail = IssueDetail.fake().model_copy(update={"description": escaped})
    snapshot = IssueSnapshot.fake().model_copy(update={"detail": detail})
    rendered = IssueNote.rendered(snapshot)
    Assert.that(rendered.root).contains(link.root)
    Assert.that(
        Assert.that(IssueNote.parsed(rendered)).is_ok().update_of(detail, NoteTitle.fake())
    ).matches(IssueUpdate.nothing())


def test_a_rendered_note_holds_the_description_as_its_body() -> None:
    rendered = IssueNote.rendered(IssueSnapshot.fake())
    Assert.that(rendered.root).ends_with(f"---\n\n{IssueDescription.fake().root}\n")


def test_a_renamed_note_updates_the_title() -> None:
    title = IssueTitle("Add a better widget")
    note = Assert.that(IssueNote.parsed(IssueNote.rendered(IssueSnapshot.fake()))).is_ok()
    Assert.that(note.update_of(IssueDetail.fake(), NoteTitle(title.root))).matches(
        IssueUpdate.nothing().model_copy(update={"title": title})
    )


def test_a_title_differing_only_where_a_file_name_cannot_hold_it_changes_nothing() -> None:
    detail = IssueDetail.fake().model_copy(update={"title": IssueTitle("Ads: v2 [draft]")})
    note = Assert.that(IssueNote.parsed(IssueNote.rendered(IssueSnapshot.fake()))).is_ok()
    Assert.that(note.update_of(detail, NoteTitle("Ads- v2 -draft-"))).matches(IssueUpdate.nothing())


def test_a_note_named_without_a_title_leaves_the_title_alone() -> None:
    note = Assert.that(IssueNote.parsed(IssueNote.rendered(IssueSnapshot.fake()))).is_ok()
    Assert.that(note.update_of(IssueDetail.fake(), None)).matches(IssueUpdate.nothing())


def test_a_title_reserved_characters_become_dashes() -> None:
    expected = NoteTitle("a-b-c-d-e-f-g-h")
    Assert.that(NoteTitle.of(IssueTitle("a/b:c[d]e#f^g|h"))).matches(expected)


def test_a_long_title_is_cut_short() -> None:
    Assert.that(len(NoteTitle.of(IssueTitle("x" * 300)).root.encode()) <= 200).is_true()


def test_a_rendered_note_holds_no_title() -> None:
    Assert.that("title:" in IssueNote.rendered(IssueSnapshot.fake()).root).is_false()


def test_an_edited_body_updates_the_description() -> None:
    description = IssueDescription("The dashboard needs two widgets.")
    text = edited(
        IssueNote.rendered(IssueSnapshot.fake()),
        Fragment(IssueDescription.fake().root),
        Fragment(description.root),
    )
    Assert.that(update_of(text)).matches(
        IssueUpdate.nothing().model_copy(update={"description": description})
    )


def test_an_edited_status_priority_and_labels_update_the_issue() -> None:
    status = IssueStatusName("Done")
    labels = LabelNames((LabelName("Backend"),))
    text = NoteText(
        f"---\nstatus: {status.root}\n"
        f"labels: [{labels.root[0].root}]\npriority: urgent\n---\n\n"
        f"{IssueDescription.fake().root}\n"
    )
    Assert.that(update_of(text)).matches(
        IssueUpdate.nothing().model_copy(
            update={"status": status, "labels": labels, "priority": Priority.urgent}
        )
    )


def test_a_status_differing_only_in_case_changes_nothing() -> None:
    text = edited(
        IssueNote.rendered(IssueSnapshot.fake()),
        Fragment(f"status: {IssueStatusName.fake().root}"),
        Fragment(f"status: {IssueStatusName.fake().root.upper()}"),
    )
    Assert.that(update_of(text)).matches(IssueUpdate.nothing())


def test_an_emptied_assignee_unassigns_the_issue() -> None:
    detail = IssueDetail.fake().model_copy(update={"assignee": Assignee.fake()})
    snapshot = IssueSnapshot.fake().model_copy(update={"detail": detail})
    text = edited(
        IssueNote.rendered(snapshot),
        Fragment(f"assignee: {Assignee.fake().root}"),
        Fragment("assignee:"),
    )
    Assert.that(
        Assert.that(IssueNote.parsed(text)).is_ok().update_of(detail, NoteTitle.fake())
    ).matches(IssueUpdate.nothing().model_copy(update={"assignee": Cleared()}))


def test_an_emptied_label_list_removes_every_label() -> None:
    text = edited(
        IssueNote.rendered(IssueSnapshot.fake()),
        Fragment(f"labels:\n- {LabelName.fake().root}"),
        Fragment("labels:"),
    )
    Assert.that(update_of(text)).matches(
        IssueUpdate.nothing().model_copy(update={"labels": LabelNames(())})
    )


def test_an_edit_to_a_field_linear_owns_changes_nothing() -> None:
    text = edited(
        IssueNote.rendered(IssueSnapshot.fake()),
        Fragment("url: https://"),
        Fragment("url: http://"),
    )
    Assert.that(update_of(text)).matches(IssueUpdate.nothing())


def test_a_note_without_frontmatter_is_invalid() -> None:
    _ = Assert.that(IssueNote.parsed(NoteText("Just text\n"))).is_err(InvalidNoteError)


def test_a_note_with_broken_yaml_is_invalid() -> None:
    text = NoteText("---\nstatus: [unclosed\n---\n")
    _ = Assert.that(IssueNote.parsed(text)).is_err(InvalidNoteError)


def test_a_note_without_a_status_is_invalid() -> None:
    text = NoteText("---\nlabels: []\n---\n")
    _ = Assert.that(IssueNote.parsed(text)).is_err(InvalidNoteError)


def test_a_nested_list_renders_with_tabs_and_reads_back_as_no_change() -> None:
    linear = IssueDescription("* My item\n  * My item 2")
    obsidian = Fragment("* My item\n\t* My item 2")
    detail = IssueDetail.fake().model_copy(update={"description": linear})
    snapshot = IssueSnapshot.fake().model_copy(update={"detail": detail})
    rendered = IssueNote.rendered(snapshot)
    Assert.that(rendered.root).contains(obsidian.root)
    Assert.that(
        Assert.that(IssueNote.parsed(rendered)).is_ok().update_of(detail, NoteTitle.fake())
    ).matches(IssueUpdate.nothing())


def test_a_nested_list_added_in_obsidian_reaches_linear_indented_with_spaces() -> None:
    linear = IssueDescription(f"* {IssueDescription.fake().root}\n  * Sized to fit")
    text = edited(
        IssueNote.rendered(IssueSnapshot.fake()),
        Fragment(IssueDescription.fake().root),
        Fragment(f"* {IssueDescription.fake().root}\n\t* Sized to fit"),
    )
    Assert.that(update_of(text).description).matches(linear)
