from mb_workflow.b_core.d_domain_model.issue import IssueDetail
from mb_workflow.d_lib.models import Value


class TicketReport(Value[str]):
    @staticmethod
    def fake() -> TicketReport:
        return TicketReport.of(IssueDetail.fake())

    @staticmethod
    def of(detail: IssueDetail) -> TicketReport:
        issue = detail.issue
        labels = issue.labels.root
        fields = (
            f"{issue.identifier.root} {detail.title.root}",
            f"status: {issue.status.root}",
            *((f"project: {issue.project.root}",) if issue.project is not None else ()),
            *((f"labels: {', '.join(label.root for label in labels)}",) if labels else ()),
        )
        body = ("", detail.description.root) if detail.description is not None else ()
        return TicketReport("".join(f"{line}\n" for line in (*fields, *body)))
