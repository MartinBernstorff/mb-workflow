from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    ConfigPath,
    Configuration,
    LinearTracker,
    PoolSettings,
    Settings,
    TicketTracker,
    WorkspaceSettings,
)
from mb_workflow.b_core.d_domain_model.issue import ProjectName, TeamKey
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def test_reports_the_resolved_tracker_and_the_file_it_came_from() -> None:
    assert ConfigReport.of(Configuration.fake()).root == (
        "tracker: todoist\n"
        "project tag: it-mb-workflow\n"
        "status store: orca\n"
        "orca project: github:flowbasedk/flowbase\n"
        "assignee: mab@flowbase.io\n"
        "claim label: claimed\n"
        "origin: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml"
    )


def test_a_linear_configuration_reports_no_project_tag() -> None:
    config = Configuration(
        settings=Settings(
            issues=LinearTracker.fake(),
            workspace=WorkspaceSettings.fake(),
            ticket_statuses=TicketStatuses.fake(),
        ),
        origin=ConfigPath.fake(),
    )
    report = ConfigReport.of(config)
    assert "tracker: linear" in report.root
    assert "project tag" not in report.root


def test_a_linear_configuration_reports_the_team_and_project_it_creates_tickets_in() -> None:
    config = Configuration(
        settings=Settings(
            issues=LinearTracker(
                tracker=TicketTracker.linear, team=TeamKey("MB"), project=ProjectName("mb-workflow")
            ),
            workspace=WorkspaceSettings.fake(),
            ticket_statuses=TicketStatuses.fake(),
        ),
        origin=ConfigPath.fake(),
    )
    report = ConfigReport.of(config).root
    assert "team: MB" in report
    assert "project: mb-workflow" in report


def test_a_configured_pool_reports_its_view() -> None:
    config = Configuration(
        settings=Settings(
            issues=LinearTracker.fake(),
            workspace=WorkspaceSettings.fake(),
            pool=PoolSettings.fake(),
            ticket_statuses=TicketStatuses.fake(),
        ),
        origin=ConfigPath.fake(),
    )
    assert f"pool view: {PoolSettings.fake().view.root}" in ConfigReport.of(config).root


def test_a_configured_pool_reports_its_limits() -> None:
    config = Configuration(
        settings=Settings(
            issues=LinearTracker.fake(),
            workspace=WorkspaceSettings.fake(),
            pool=PoolSettings.fake(),
            ticket_statuses=TicketStatuses.fake(),
        ),
        origin=ConfigPath.fake(),
    )
    assert "pool limits: total 4, Grilling 1" in ConfigReport.of(config).root
