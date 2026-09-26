from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import pick_listing
from mb_workflow.b_core.d_domain_model.flow_labels import FlowLabels
from mb_workflow.b_core.d_domain_model.issue import GroupedLabels, IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority


def test_the_listing_names_each_ready_ticket_its_priority_and_state_in_order() -> None:
    urgent = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-2")}
            ),
            "priority": Priority.urgent,
        }
    )
    unprioritised = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-1")}
            ),
            "priority": Priority.no_priority,
        }
    )
    assert pick_listing(PoolTickets((urgent, unprioritised)), FlowLabels.fake()) == Output(
        "E-2\turgent\tSpecced\nE-1\tno_priority\tSpecced\n"
    )


def test_the_listing_marks_a_ticket_without_a_flow_label_as_stateless() -> None:
    unlabelled = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-3"), "grouped": GroupedLabels(())}
            )
        }
    )
    assert pick_listing(PoolTickets((unlabelled,)), FlowLabels.fake()) == Output("E-3\tmedium\t-\n")
