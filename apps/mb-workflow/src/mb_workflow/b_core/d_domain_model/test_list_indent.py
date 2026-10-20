import re

from assertions import Assert
from hypothesis import given
from hypothesis import strategies as st

from mb_workflow.b_core.d_domain_model.issue import IssueDescription
from mb_workflow.b_core.d_domain_model.list_indent import ListIndent

MARKERS = st.sampled_from(["*", "-", "1.", "10.", "2)", "- [ ]"])
WORDS = st.text(alphabet="ab *-.1[]`\t", max_size=8).map(str.strip)


# Lists as Obsidian writes them: each item at most one level deeper than the one before, with
# paragraphs and code fences between lists.
@st.composite
def obsidian_descriptions(draw: st.DrawFn) -> IssueDescription:
    lines: list[str] = []
    for _ in range(draw(st.integers(min_value=1, max_value=4))):
        depth = -1
        for _ in range(draw(st.integers(min_value=1, max_value=6))):
            depth = draw(st.integers(min_value=0, max_value=depth + 1))
            lines.append(f"{'\t' * depth}{draw(MARKERS)} {draw(WORDS)}")
        lines.append(draw(st.sampled_from(["", "Text", "```\n  * code\n```"])))
    return IssueDescription("\n".join(lines))


def test_linear_nests_an_item_under_its_parents_text() -> None:
    obsidian = IssueDescription("* My item\n\t* My item 2\n\t\t1. Three\n\t\t\t* Four")
    linear = IssueDescription("* My item\n  * My item 2\n    1. Three\n       * Four")
    Assert.that(ListIndent.linear.indented(obsidian)).matches(linear)
    Assert.that(ListIndent.obsidian.indented(linear)).matches(obsidian)


def test_obsidian_drops_the_blank_line_linear_puts_between_a_paragraph_and_a_list() -> None:
    linear = IssueDescription("My line:\n\n* My item\n  * My item 2")
    obsidian = IssueDescription("My line:\n* My item\n\t* My item 2")
    Assert.that(ListIndent.obsidian.indented(linear)).matches(obsidian)


def test_a_blank_line_after_a_heading_or_code_fence_stays() -> None:
    spaced = IssueDescription("# Heading\n\n* Item\n```\ncode\n```\n\n* Item")
    Assert.that(ListIndent.obsidian.indented(spaced)).matches(spaced)


def test_an_item_indented_with_both_tabs_and_spaces_nests_where_obsidian_shows_it() -> None:
    mixed = IssueDescription("* Errors\n\t  * Caught by Sentry")
    obsidian = IssueDescription("* Errors\n\t* Caught by Sentry")
    Assert.that(ListIndent.obsidian.indented(mixed)).matches(obsidian)


def test_a_code_fence_keeps_its_indentation() -> None:
    fenced = IssueDescription("* Item\n```\n  * code\n\t* code\n```")
    Assert.that(ListIndent.obsidian.indented(fenced)).matches(fenced)
    Assert.that(ListIndent.linear.indented(fenced)).matches(fenced)


@given(obsidian_descriptions())
def test_obsidian_lists_survive_a_round_trip_through_linear(obsidian: IssueDescription) -> None:
    Assert.that(ListIndent.obsidian.indented(obsidian)).matches(obsidian)
    Assert.that(ListIndent.obsidian.indented(ListIndent.linear.indented(obsidian))).matches(
        obsidian
    )


@given(obsidian_descriptions())
def test_linear_lists_survive_a_round_trip_through_obsidian(obsidian: IssueDescription) -> None:
    linear = ListIndent.linear.indented(obsidian)
    Assert.that(ListIndent.linear.indented(linear)).matches(linear)
    Assert.that(ListIndent.linear.indented(ListIndent.obsidian.indented(linear))).matches(linear)


# Linear stores a list that follows a paragraph with a blank line between them.
def stored_by_linear(description: IssueDescription) -> IssueDescription:
    return IssueDescription(
        re.sub(r"^(Text\n)(?=[-*\d])", r"\1\n", description.root, flags=re.MULTILINE)
    )


@given(obsidian_descriptions())
def test_obsidian_lists_survive_linear_spacing_them_from_a_paragraph(
    obsidian: IssueDescription,
) -> None:
    stored = stored_by_linear(ListIndent.linear.indented(obsidian))
    Assert.that(ListIndent.obsidian.indented(stored)).matches(obsidian)


@given(st.text(alphabet=" \t\n*-+1.)ab`~", max_size=60).map(IssueDescription))
def test_any_text_reaches_a_fixed_point_after_one_conversion(text: IssueDescription) -> None:
    obsidian = ListIndent.obsidian.indented(text)
    Assert.that(ListIndent.obsidian.indented(ListIndent.linear.indented(obsidian))).matches(
        obsidian
    )
