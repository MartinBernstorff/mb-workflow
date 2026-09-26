from subprocess import CalledProcessError
from typing import TYPE_CHECKING, override

from pydantic import AliasPath, Field, ValidationError

from mb_workflow.b_core.c_secondary_ports.issue_tracker import IssueTracker, IssueTrackerError
from mb_workflow.b_core.d_domain_model.issue import (
    Assigned,
    Issue,
    IssueIdentifier,
    Issues,
    LabelName,
    LabelNames,
    ProjectName,
    StatusName,
)
from mb_workflow.c_infrastructure.shell import Command, CommandOutput
from mb_workflow.d_lib.models import Payload, Value

if TYPE_CHECKING:
    from collections.abc import Callable

    from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueFilter
    from mb_workflow.c_infrastructure.shell import CommandRunner


class LabelPayload(Payload):
    name: LabelName

    @staticmethod
    def fake() -> LabelPayload:
        return LabelPayload(name=LabelName.fake())


class LabelPayloads(Value[tuple[LabelPayload, ...]]):
    @staticmethod
    def fake() -> LabelPayloads:
        return LabelPayloads((LabelPayload.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> LabelPayloads:
        return LabelPayloads.model_validate_json(output.root)

    def names(self) -> LabelNames:
        return LabelNames(tuple(label.name for label in self.root))


class ProjectPayload(Payload):
    name: ProjectName

    @staticmethod
    def fake() -> ProjectPayload:
        return ProjectPayload(name=ProjectName.fake())


# Only whether someone is assigned matters, so none of the assignee's fields are read.
class AssigneePayload(Payload):
    @staticmethod
    def fake() -> AssigneePayload:
        return AssigneePayload()


class IssuePayload(Payload):
    identifier: IssueIdentifier
    status: StatusName = Field(validation_alias=AliasPath("state", "name"))
    project: ProjectPayload | None = None
    labels: tuple[LabelPayload, ...] = Field(
        default=(), validation_alias=AliasPath("labels", "nodes")
    )
    assignee: AssigneePayload | None = None

    @staticmethod
    def fake() -> IssuePayload:
        return IssuePayload(
            identifier=IssueIdentifier.fake(),
            status=StatusName.fake(),
            project=ProjectPayload.fake(),
            labels=(LabelPayload.fake(),),
        )

    @staticmethod
    def parse(output: CommandOutput) -> IssuePayload:
        return IssuePayload.model_validate_json(output.root)

    def issue(self) -> Issue:
        return Issue(
            identifier=self.identifier,
            status=self.status,
            project=self.project.name if self.project is not None else None,
            labels=LabelNames(tuple(label.name for label in self.labels)),
            assigned=Assigned(self.assignee is not None),
        )


class IssuePayloads(Value[tuple[IssuePayload, ...]]):
    @staticmethod
    def fake() -> IssuePayloads:
        return IssuePayloads((IssuePayload.fake(),))

    @staticmethod
    def parse(output: CommandOutput) -> IssuePayloads:
        return IssuePayloads.model_validate_json(output.root)

    def issues(self) -> Issues:
        return Issues(tuple(payload.issue() for payload in self.root))


class LinearCli(IssueTracker):
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    @override
    def workspace_labels(self) -> LabelNames:
        lookup = self._command(Command(("labels", "list", "--type", "issue", "--all")))
        return self._parsed(LabelPayloads.parse, lookup).names()

    # `issues list` can filter by neither creator nor exact creation date, so this asks GraphQL.
    @override
    def issues(self, wanted: IssueFilter) -> Issues:
        lookup = self._command(
            Command(
                (
                    "api",
                    "query",
                    "--paginate",
                    "--nodes-path",
                    "data.issues.nodes",
                    "--page-info-path",
                    "data.issues.pageInfo",
                    "--variable",
                    f"creator={wanted.creator.root}",
                    "--variable",
                    f"since={wanted.created_after.root.isoformat()}",
                    """
            query($creator: String!, $since: DateTimeOrDuration!, $first: Int, $after: String) {
              issues(
                first: $first
                after: $after
                filter: { creator: { email: { eq: $creator } }, createdAt: { gte: $since } }
              ) {
                nodes {
                  identifier
                  state { name }
                  project { name }
                  labels { nodes { name } }
                  assignee { id }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
            """,
                )
            )
        )
        return self._parsed(IssuePayloads.parse, lookup).issues()

    @override
    def read(self, issue: IssueIdentifier) -> Issue:
        return self._parsed(
            IssuePayload.parse, self._command(Command(("issues", "get", issue.root)))
        ).issue()

    @override
    def add_label(self, issue: IssueIdentifier, label: LabelName) -> None:
        current = self.read(issue).labels
        if current.matching(label) is not None:
            return
        self.set_labels(issue, LabelNames((*current.root, label)))

    # linear-cli overwrites the labels it is given, and only raw input can send an empty set.
    @override
    def set_labels(self, issue: IssueIdentifier, labels: LabelNames) -> None:
        if len(labels.root) == 0:
            _ = self._run(
                self._command(
                    Command(("issues", "update", issue.root, "--data", '{"labelIds":[]}'))
                )
            )
            return
        flags = tuple(flag for label in labels.root for flag in ("--labels", label.root))
        _ = self._run(self._command(Command(("issues", "update", issue.root, *flags))))

    @override
    def assign(self, issue: IssueIdentifier, assignee: Assignee) -> None:
        _ = self._run(
            self._command(Command(("issues", "update", issue.root, "--assignee", assignee.root)))
        )

    # The label list is cached by linear-cli, which would hide a label created since.
    @staticmethod
    def _command(arguments: Command) -> Command:
        return Command(("linear-cli", "--output", "json", "--no-cache", *arguments.root))

    def _run(self, command: Command) -> CommandOutput:
        try:
            return self._runner.run(command)
        except CalledProcessError as error:
            raise IssueTrackerError(f"{error} {error.stderr}".strip()) from error
        except FileNotFoundError as error:
            raise IssueTrackerError(f"{error.filename} is not installed or not on PATH.") from error

    def _parsed[T](self, parse: Callable[[CommandOutput], T], command: Command) -> T:
        output = self._run(command)
        try:
            return parse(output)
        except ValidationError as error:
            raise IssueTrackerError(
                f"linear-cli answered in an unexpected shape: {error}"
            ) from error
