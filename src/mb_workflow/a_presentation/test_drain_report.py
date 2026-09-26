from mb_workflow.a_presentation.console import Output
from mb_workflow.a_presentation.drain_report import pick_listing
from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier
from mb_workflow.b_core.d_domain_model.pool import PoolTicket, PoolTickets, Priority


def test_the_listing_names_each_ready_ticket_its_priority_and_state_in_order() -> None:
    urgent = PoolTicket.fake().model_copy(update={"priority": Priority.urgent})
    unprioritised = PoolTicket.fake().model_copy(
        update={
            "issue": PoolTicket.fake().issue.model_copy(
                update={"identifier": IssueIdentifier("E-1")}
            ),
            "priority": Priority.no_priority,
        }
    )
    assert pick_listing(PoolTickets((urgent, unprioritised))) == Output(
        "E-4289\turgent\tSpecced\nE-1\tno_priority\tSpecced\n"
    )
