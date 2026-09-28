from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    ConfigPath,
    Configuration,
    LinearTracker,
    PoolSettings,
    Settings,
    WorkspaceSettings,
)
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def test_reports_the_file_it_came_from_and_every_resolved_setting() -> None:
    assert ConfigReport.of(Configuration.fake()).root == (
        "origin: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml\n"
        "tracker: todoist\n"
        "project tag: it-mb-workflow\n"
        "status store: orca\n"
        "orca project: github:flowbasedk/flowbase\n"
        "assignee: mab@flowbase.io\n"
        "claim label: claimed\n"
        "ticket statuses:\n"
        "  Grilling: Maturing\n"
        "  Speccing: Maturing\n"
        "  Specced: Todo\n"
        "  Implementing: In Progress\n"
        "  QA: In Progress\n"
        "  Review: In Review\n"
        "  Merging: Ready For Release\n"
        "  Merged: Done"
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
