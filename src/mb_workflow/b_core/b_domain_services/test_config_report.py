from mb_workflow.b_core.b_domain_services.config_report import ConfigReport
from mb_workflow.b_core.d_domain_model.config import (
    Configuration,
    LinearTracker,
    PoolSettings,
    Settings,
    TicketTracker,
    WorkspaceSettings,
)
from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingsTable,
)
from mb_workflow.b_core.d_domain_model.issue import ProjectName, TeamKey
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses


def test_reports_the_file_it_came_from_and_every_resolved_setting() -> None:
    assert ConfigReport.of(Configuration.fake()).root == (
        "repo file: /Users/me/orca/workspaces/mb-workflow/mb-workflow.toml\n"
        "override file: none (no file at"
        " /Users/me/.config/mb-workflow/projects/MartinBernstorff/mb-workflow.toml)\n"
        "tracker: todoist (repo)\n"
        "project tag: it-mb-workflow (repo)\n"
        "status store: orca (repo)\n"
        "orca project: github:flowbasedk/flowbase (repo)\n"
        "assignee: mab@flowbase.io (repo)\n"
        "claim label: claimed (repo)\n"
        "ticket statuses:\n"
        "  Grilling: Maturing (repo)\n"
        "  Speccing: Maturing (repo)\n"
        "  Specced: Todo (repo)\n"
        "  Implementing: In Progress (repo)\n"
        "  QA: In Progress (repo)\n"
        "  Review: In Review (repo)\n"
        "  Merging: Ready For Release (repo)\n"
        "  Merged: Done (repo)"
    )


def test_a_linear_configuration_reports_no_project_tag() -> None:
    config = Configuration.fake().model_copy(
        update={
            "settings": Settings(
                issues=LinearTracker.fake(),
                workspace=WorkspaceSettings.fake(),
                ticket_statuses=TicketStatuses.fake(),
            )
        }
    )
    report = ConfigReport.of(config)
    assert "tracker: linear" in report.root
    assert "project tag" not in report.root


def test_a_linear_configuration_reports_the_team_and_project_it_creates_tickets_in() -> None:
    config = Configuration.fake().model_copy(
        update={
            "settings": Settings(
                issues=LinearTracker(
                    tracker=TicketTracker.linear,
                    team=TeamKey("MB"),
                    project=ProjectName("mb-workflow"),
                ),
                workspace=WorkspaceSettings.fake(),
                ticket_statuses=TicketStatuses.fake(),
            )
        }
    )
    report = ConfigReport.of(config).root
    assert "team: MB" in report
    assert "project: mb-workflow" in report


def test_a_configured_pool_reports_its_view() -> None:
    config = Configuration.fake().model_copy(
        update={
            "settings": Settings(
                issues=LinearTracker.fake(),
                workspace=WorkspaceSettings.fake(),
                pool=PoolSettings.fake(),
                ticket_statuses=TicketStatuses.fake(),
            )
        }
    )
    assert f"pool view: {PoolSettings.fake().view.root}" in ConfigReport.of(config).root


def test_a_configured_pool_reports_its_limits() -> None:
    config = Configuration.fake().model_copy(
        update={
            "settings": Settings(
                issues=LinearTracker.fake(),
                workspace=WorkspaceSettings.fake(),
                pool=PoolSettings.fake(),
                ticket_statuses=TicketStatuses.fake(),
            )
        }
    )
    assert "pool limits: total 4, Grilling 1 (default)" in ConfigReport.of(config).root


def test_a_configured_pool_reports_its_skip_limits_label() -> None:
    config = Configuration.fake().model_copy(
        update={
            "settings": Settings(
                issues=LinearTracker.fake(),
                workspace=WorkspaceSettings.fake(),
                pool=PoolSettings.fake(),
                ticket_statuses=TicketStatuses.fake(),
            )
        }
    )
    assert "pool skip-limits label: skip-limits (default)" in ConfigReport.of(config).root


def test_lists_the_override_file_it_read() -> None:
    config = Configuration.fake().model_copy(update={"override": OverrideFile.fake()})
    assert f"override file: {OverridePath.fake().root}\n" in ConfigReport.of(config).root


def test_notes_when_no_origin_remote_names_an_override_file() -> None:
    config = Configuration.fake().model_copy(update={"override": NoOverrideFile(expected=None)})
    assert "override file: none (no origin remote" in ConfigReport.of(config).root


def test_attributes_an_overridden_setting_to_the_override_file() -> None:
    config = Configuration.fake().model_copy(
        update={
            "override": OverrideFile(
                path=OverridePath.fake(),
                table=SettingsTable({"workspace": {"assignee": "mab@flowbase.io"}}),
            )
        }
    )
    report = ConfigReport.of(config).root
    assert "assignee: mab@flowbase.io (override)" in report
    assert "orca project: github:flowbasedk/flowbase (repo)" in report


def test_attributes_a_table_set_in_both_files_to_both() -> None:
    settings = Settings(
        issues=LinearTracker.fake(),
        workspace=WorkspaceSettings.fake(),
        pool=PoolSettings.fake(),
        ticket_statuses=TicketStatuses.fake(),
    )
    config = Configuration.fake().model_copy(
        update={
            "settings": settings,
            "table": SettingsTable({"pool": {"view": "4efb86b38740", "limits": {"total": 4}}}),
            "override": OverrideFile(
                path=OverridePath.fake(),
                table=SettingsTable({"pool": {"limits": {"states": {"Grilling": 1}}}}),
            ),
        }
    )
    assert "pool limits: total 4, Grilling 1 (repo+override)" in ConfigReport.of(config).root
