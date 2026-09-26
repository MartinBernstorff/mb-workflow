import logging

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    IssueDescription,
    IssueIdentifier,
    IssueTitle,
    LabelName,
    LabelNames,
    MilestoneName,
    ProjectName,
    StatusName,
)
from mb_workflow.b_core.d_domain_model.ticket_edit import RemoveMilestone, TicketEdit
from mb_workflow.d_lib.logging import LogLevel, configure

ticket_app = typer.Typer(no_args_is_help=True)


@ticket_app.command("view")
def ticket_view(
    issue: str = typer.Argument(..., help="Identifier of the issue to show, e.g. MB-28."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.ticket_view(IssueIdentifier(issue)).root)


@ticket_app.command("edit")
def ticket_edit(
    *,
    issue: str = typer.Argument(..., help="Identifier of the issue to edit, e.g. MB-28."),
    title: str | None = typer.Option(None, "--title", "-t", help="Set the new title."),
    body: str | None = typer.Option(None, "--body", "-b", help="Set the new body."),
    body_file: typer.FileText | None = typer.Option(
        None, "--body-file", "-F", help='Read body text from file (use "-" to read from stdin).'
    ),
    add_label: list[str] = typer.Option([], "--add-label", help="Add labels by name."),
    remove_label: list[str] = typer.Option([], "--remove-label", help="Remove labels by name."),
    add_assignee: str | None = typer.Option(
        None, "--add-assignee", help='Assign a person by email. Use "@me" to self-assign.'
    ),
    remove_assignee: str | None = typer.Option(
        None,
        "--remove-assignee",
        help='Unassign a person by email. Use "@me" to unassign yourself.',
    ),
    add_project: str | None = typer.Option(None, "--add-project", help="Move to a project."),
    remove_project: str | None = typer.Option(
        None, "--remove-project", help="Remove from a project."
    ),
    state: str | None = typer.Option(None, "--state", "-s", help="Move to a workflow state."),
    milestone: str | None = typer.Option(None, "--milestone", "-m", help="Set the milestone."),
    remove_milestone: bool = typer.Option(
        False, "--remove-milestone", help="Remove the milestone."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    edit = TicketEdit(
        title=IssueTitle.from_nullable(title),
        body=IssueDescription.from_nullable(body),
        body_file=IssueDescription(body_file.read()) if body_file is not None else None,
        add_labels=LabelNames(tuple(map(LabelName, add_label))).split(),
        remove_labels=LabelNames(tuple(map(LabelName, remove_label))).split(),
        add_assignee=Assignee.from_nullable(add_assignee),
        remove_assignee=Assignee.from_nullable(remove_assignee),
        add_project=ProjectName.from_nullable(add_project),
        remove_project=ProjectName.from_nullable(remove_project),
        status=StatusName.from_nullable(state),
        milestone=MilestoneName.from_nullable(milestone),
        remove_milestone=RemoveMilestone(remove_milestone),
    )
    raise typer.Exit(code=commands.ticket_edit(IssueIdentifier(issue), edit).root)
