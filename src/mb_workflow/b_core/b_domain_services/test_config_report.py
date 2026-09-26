from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    ConfigPath,
    Configuration,
    LinearTracker,
    Settings,
    WorkspaceSettings,
)


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
        settings=Settings(issues=LinearTracker.fake(), workspace=WorkspaceSettings.fake()),
        origin=ConfigPath.fake(),
    )
    report = ConfigReport.of(config)
    assert "tracker: linear" in report.root
    assert "project tag" not in report.root
