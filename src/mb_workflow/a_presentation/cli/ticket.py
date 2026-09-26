import logging
from pathlib import Path

import typer

from mb_workflow.a_presentation import commands
from mb_workflow.b_core.a_features.autolabel import (
    AutolabelRequest,
    DryRun,
    ExcludePattern,
    Exclusions,
    LedgerPath,
)
from mb_workflow.b_core.a_features.edit_issue import BodyFile, EditRequest, RemoveMilestone
from mb_workflow.b_core.d_domain_model.cache import CacheDirectory
from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    CreatedAfter,
    CreatedWithin,
    Creator,
    IssueBody,
    IssueFilter,
    IssueReference,
    IssueTitle,
    LabelName,
    LabelNames,
    MilestoneName,
    ProjectName,
)
from mb_workflow.d_lib.logging import LogLevel, configure

app = typer.Typer(no_args_is_help=True)


@app.command("edit")
def edit(
    *,
    target: str = typer.Argument(
        "", help="Issue identifier or URL. Defaults to the worktree's linked issue."
    ),
    title: str | None = typer.Option(None, "--title", "-t"),
    body: str | None = typer.Option(None, "--body", "-b"),
    body_file: str | None = typer.Option(
        None, "--body-file", "-F", help='Read the body from a file; "-" reads stdin.'
    ),
    add_label: list[str] = typer.Option([], "--add-label", help="Names, comma-separated."),
    remove_label: list[str] = typer.Option([], "--remove-label", help="Names, comma-separated."),
    add_assignee: str | None = typer.Option(
        None, "--add-assignee", help='Email or "@me"; replaces the current assignee.'
    ),
    remove_assignee: str | None = typer.Option(None, "--remove-assignee", help='Email or "@me".'),
    add_project: str | None = typer.Option(
        None, "--add-project", help="Replaces the current project."
    ),
    remove_project: str | None = typer.Option(None, "--remove-project"),
    milestone: str | None = typer.Option(None, "--milestone", "-m"),
    remove_milestone: bool = typer.Option(False, "--remove-milestone"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    request = EditRequest(
        target=IssueReference(target) if target else None,
        title=IssueTitle(title) if title is not None else None,
        body=IssueBody(body) if body is not None else None,
        body_file=BodyFile(Path(body_file)) if body_file is not None else None,
        add_labels=LabelNames(tuple(LabelName(label) for label in add_label)),
        remove_labels=LabelNames(tuple(LabelName(label) for label in remove_label)),
        add_assignee=Assignee(add_assignee) if add_assignee is not None else None,
        remove_assignee=Assignee(remove_assignee) if remove_assignee is not None else None,
        add_project=ProjectName(add_project) if add_project is not None else None,
        remove_project=ProjectName(remove_project) if remove_project is not None else None,
        milestone=MilestoneName(milestone) if milestone is not None else None,
        remove_milestone=RemoveMilestone(remove_milestone),
    )
    raise typer.Exit(code=commands.ticket_edit(request).root)


@app.command("label")
@app.command("l")
def label(
    name: str = typer.Argument(..., help="Label to add to the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.ticket_edit(EditRequest.labelling(LabelName(name))).root)


@app.command("unlabel")
@app.command("ul")
def unlabel(
    name: str = typer.Argument(..., help="Label to remove from the linked issue."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    raise typer.Exit(code=commands.ticket_edit(EditRequest.unlabelling(LabelName(name))).root)


@app.command("autolabel")
def autolabel(
    *,
    name: str = typer.Argument(..., help="Label to add to the swept issues."),
    creator: str = typer.Option(..., "--creator"),
    exclude_projects: str = typer.Option("", "--exclude-projects"),
    exclude_statuses: str = typer.Option("", "--exclude-statuses"),
    created_within_days: int = typer.Option(30, "--created-within-days"),
    apply: bool = typer.Option(False, "--apply"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    configure(LogLevel(logging.WARNING if quiet else logging.INFO))
    label = LabelName(name)
    request = AutolabelRequest(
        label=label,
        wanted=IssueFilter(
            creator=Creator(creator),
            created_after=CreatedAfter.of(CreatedWithin(created_within_days), Today.now()),
        ),
        exclusions=Exclusions(
            projects=ExcludePattern(exclude_projects) if exclude_projects else None,
            statuses=ExcludePattern(exclude_statuses) if exclude_statuses else None,
        ),
        dry_run=DryRun(not apply),
    )
    ledger = LedgerPath.of(CacheDirectory.of_user(), label)
    raise typer.Exit(code=commands.ticket_autolabel(request, ledger).root)
