import logging
from enum import StrEnum
from pathlib import Path

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.a_presentation.cli.group import AlphabeticalGroup
from mb_workflow.b_core.a_features.autolabel import AutolabelRequest, DryRun
from mb_workflow.b_core.d_domain_model.autolabel import ExcludePattern, Exclusions
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.config import ConfigFileName, WorkingDirectory
from mb_workflow.b_core.d_domain_model.flow import AcceptedStates, StateName, WorkflowChart
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    CreatedAfter,
    CreatedWithin,
    Creator,
    IssueDescription,
    IssueIdentifier,
    IssueTitle,
    LabelName,
    LabelNames,
    MilestoneName,
    Priority,
    ProjectName,
)
from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDraft
from mb_workflow.b_core.d_domain_model.ticket_edit import RemoveMilestone, TicketEdit
from mb_workflow.d_lib.logging import LogLevel

ticket_app = typer.Typer(no_args_is_help=True, cls=AlphabeticalGroup)


class PriorityChoice(StrEnum):
    no_priority = "none"
    urgent = "urgent"
    high = "high"
    medium = "medium"
    low = "low"

    def to_priority(self) -> Priority:
        return Priority[self.name]


@ticket_app.command("view")
def ticket_view(
    issue: str = typer.Argument(..., help="Identifier of the issue to show, e.g. MB-28."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    LogLevel(logging.WARNING if quiet else logging.INFO).configure()
    raise typer.Exit(code=commands.ticket_view(IssueIdentifier(issue)).root)


@ticket_app.command("create")
def ticket_create(
    *,
    title: str = typer.Option(..., "--title", "-t", help="Supply a title."),
    body: str | None = typer.Option(None, "--body", "-b", help="Supply a body."),
    body_file: typer.FileText | None = typer.Option(
        None, "--body-file", "-F", help='Read body text from file (use "-" to read from stdin).'
    ),
    label: list[str] = typer.Option([], "--label", "-l", help="Add labels by name."),
    assignee: str | None = typer.Option(
        None, "--assignee", "-a", help='Assign a person by email. Use "@me" to self-assign.'
    ),
    milestone: str | None = typer.Option(
        None, "--milestone", "-m", help="Add the ticket to a milestone by name."
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Add the ticket to a project, overriding the config."
    ),
    priority: PriorityChoice | None = typer.Option(
        None, "--priority", help='Set the priority. Use "none" to clear it.', case_sensitive=False
    ),
    blocks: list[str] = typer.Option([], "--blocks", help="Mark the ticket as blocking an issue."),
    blocked_by: list[str] = typer.Option(
        [], "--blocked-by", help="Mark the ticket as blocked by an issue."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    LogLevel(logging.WARNING if quiet else logging.INFO).configure()
    draft = TicketDraft(
        title=IssueTitle(title),
        body=IssueDescription.from_nullable(body),
        body_file=IssueDescription(body_file.read()) if body_file is not None else None,
        labels=LabelNames(tuple(map(LabelName, label))).split(),
        assignee=Assignee.from_nullable(assignee),
        project=ProjectName.from_nullable(project),
        milestone=MilestoneName.from_nullable(milestone),
        priority=priority.to_priority() if priority is not None else None,
        blocks=tuple(map(IssueIdentifier, blocks)),
        blocked_by=tuple(map(IssueIdentifier, blocked_by)),
    )
    raise typer.Exit(
        code=commands.ticket_create(
            draft, WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


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
    state: str | None = typer.Option(
        None,
        "--state",
        "-s",
        help="Move to a flow state, ignoring case and the chart's allowed moves: "
        + ", ".join(state.root for state in AcceptedStates.of_chart(WorkflowChart).root)
        + ".",
    ),
    milestone: str | None = typer.Option(None, "--milestone", "-m", help="Set the milestone."),
    remove_milestone: bool = typer.Option(
        False, "--remove-milestone", help="Remove the milestone."
    ),
    priority: PriorityChoice | None = typer.Option(
        None, "--priority", help='Set the priority. Use "none" to clear it.', case_sensitive=False
    ),
    add_blocks: list[str] = typer.Option(
        [], "--add-blocks", help="Mark the ticket as blocking an issue."
    ),
    add_blocked_by: list[str] = typer.Option(
        [], "--add-blocked-by", help="Mark the ticket as blocked by an issue."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    LogLevel(logging.WARNING if quiet else logging.INFO).configure()
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
        state=StateName.from_nullable(state),
        milestone=MilestoneName.from_nullable(milestone),
        remove_milestone=RemoveMilestone(remove_milestone),
        priority=priority.to_priority() if priority is not None else None,
        add_blocks=tuple(map(IssueIdentifier, add_blocks)),
        add_blocked_by=tuple(map(IssueIdentifier, add_blocked_by)),
    )
    raise typer.Exit(
        code=commands.ticket_edit(
            IssueIdentifier(issue), edit, WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )


@ticket_app.command("autolabel")
def autolabel(
    *,
    name: str = typer.Argument(..., help="Linear label to add to the swept issues."),
    creator: str = typer.Option(..., "--creator"),
    exclude_projects: str = typer.Option("", "--exclude-projects"),
    exclude_statuses: str = typer.Option("", "--exclude-statuses"),
    created_within_days: int = typer.Option(30, "--created-within-days"),
    apply: bool = typer.Option(False, "--apply"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    LogLevel(logging.WARNING if quiet else logging.INFO).configure()
    request = AutolabelRequest(
        label=LabelName(name),
        creator=Creator(creator),
        exclusions=Exclusions(
            projects=ExcludePattern(exclude_projects) if exclude_projects else None,
            statuses=ExcludePattern(exclude_statuses) if exclude_statuses else None,
        ),
        dry_run=DryRun(not apply),
    )
    window = CreatedAfter.of(CreatedWithin(created_within_days), Today.now())
    raise typer.Exit(code=commands.linear_autolabel(request, window).root)


@ticket_app.command("unclaim")
def unclaim(
    ticket: str = typer.Argument(..., help="Ticket whose stuck claim to release, e.g. MB-36."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    # lint-ignore: NoComment
    """Delete every claim on the ticket, whichever worktree or host placed it, and its claim label."""
    LogLevel(logging.WARNING if quiet else logging.INFO).configure()
    raise typer.Exit(
        code=commands.ticket_unclaim(
            IssueIdentifier(ticket), WorkingDirectory(Path.cwd()), ConfigFileName.default()
        ).root
    )
