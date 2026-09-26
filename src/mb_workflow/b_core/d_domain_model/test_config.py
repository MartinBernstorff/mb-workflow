from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mb_workflow.b_core.d_domain_model.config import (
    ClaimSettings,
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    LinearTracker,
    MissingConfigError,
    OrcaStatus,
    PoolSettings,
    ProjectTag,
    SearchedDirectories,
    Settings,
    StatusStore,
    TicketTracker,
    TodoistTracker,
    WorkingDirectory,
    WorkspaceSettings,
)
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.issue import Assignee, IssueStatusName, LabelName
from mb_workflow.b_core.d_domain_model.pool import Limit, PoolLimits, ViewSlug
from mb_workflow.b_core.d_domain_model.ticket_statuses import TicketStatuses
from mb_workflow.b_core.d_domain_model.workspace import ProjectSelector

if TYPE_CHECKING:
    from pydantic import JsonValue


def fake_ticket_statuses_table() -> JsonValue:
    return {state.root: status.root for state, status in TicketStatuses.fake().root.items()}


def settings_with_fake_workspace(**tables: JsonValue) -> Settings:
    workspace = WorkspaceSettings.fake().model_dump(mode="json")
    statuses = fake_ticket_statuses_table()
    return Settings.model_validate({"workspace": workspace, "ticket_statuses": statuses, **tables})


def test_the_search_starts_at_the_working_directory_and_walks_up() -> None:
    searched = SearchedDirectories.of(WorkingDirectory(Path("/a/b/c")))
    assert searched.root == (Path("/a/b/c"), Path("/a/b"), Path("/a"), Path("/"))


def test_the_nearest_configuration_file_wins(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.origin.root == tmp_path / "repo" / "src" / "mb-workflow.toml"
    assert resolved.settings.issues == TodoistTracker.fake()


def test_the_search_walks_up_when_the_working_directory_holds_no_file(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.origin.root == tmp_path / "repo" / "mb-workflow.toml"


def test_a_configuration_in_a_parent_is_not_merged_into_the_nearest_one(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-other-project"\n'
        '[workspace]\norca_project = "github:other/project"\nassignee = "other@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.settings == Settings(
        issues=LinearTracker.fake(),
        workspace=WorkspaceSettings.fake(),
        ticket_statuses=TicketStatuses.fake(),
    )


def test_an_absent_configuration_file_lists_the_directories_searched(tmp_path: Path) -> None:
    (tmp_path / "repo").mkdir()
    with pytest.raises(MissingConfigError) as raised:
        _ = Configuration.resolved(
            WorkingDirectory(tmp_path / "repo"), ConfigFileName("absent.toml")
        )
    assert "absent.toml" in str(raised.value)
    assert str(tmp_path / "repo") in str(raised.value)
    assert str(tmp_path) in str(raised.value)


def test_a_malformed_configuration_file_names_itself(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')
    with pytest.raises(InvalidConfigError) as raised:
        _ = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake())
    assert str(tmp_path / "mb-workflow.toml") in str(raised.value)


def test_a_linear_configuration_names_only_its_tracker() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    assert settings.issues == LinearTracker(tracker=TicketTracker.linear)


def test_a_todoist_configuration_names_its_project_tag() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "todoist", "project_tag": "it-mb-workflow"}
    )
    assert settings.issues == TodoistTracker(
        tracker=TicketTracker.todoist, project_tag=ProjectTag.fake()
    )


def test_a_todoist_configuration_without_a_project_tag_is_refused() -> None:
    with pytest.raises(ValueError, match=r"todoist\.project_tag"):
        _ = settings_with_fake_workspace(issues={"tracker": "todoist"})


def test_a_project_tag_without_todoist_is_refused() -> None:
    with pytest.raises(ValueError, match=r"linear\.project_tag"):
        _ = settings_with_fake_workspace(
            issues={"tracker": "linear", "project_tag": "it-mb-workflow"}
        )


def test_an_unknown_tracker_is_refused() -> None:
    with pytest.raises(ValueError, match="union_tag_invalid"):
        _ = settings_with_fake_workspace(issues={"tracker": "jira"})


def test_a_configuration_naming_no_tracker_is_refused() -> None:
    with pytest.raises(ValueError, match="issues"):
        _ = settings_with_fake_workspace()


def test_the_status_store_defaults_to_orca() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    assert settings.status == OrcaStatus(store=StatusStore.orca)


def test_an_empty_status_table_defaults_to_orca() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"}, status={})
    assert settings.status == OrcaStatus.fake()


def test_the_status_store_can_be_named_explicitly() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"}, status={"store": "orca"})
    assert settings.status == OrcaStatus.fake()


def test_an_unknown_status_store_is_refused() -> None:
    with pytest.raises(ValueError, match=r"status\.store"):
        _ = settings_with_fake_workspace(
            issues={"tracker": "linear"}, status={"store": "sticky-notes"}
        )


def test_a_setting_the_file_does_not_define_is_refused() -> None:
    with pytest.raises(ValueError, match="extra_forbidden"):
        _ = settings_with_fake_workspace(issues={"tracker": "linear"}, sttaus={"store": "orca"})


def test_the_workspace_table_names_the_orca_project_and_the_assignee() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"},
        workspace={"orca_project": "github:other/project", "assignee": "other@flowbase.io"},
    )
    assert settings.workspace == WorkspaceSettings(
        orca_project=ProjectSelector("github:other/project"),
        assignee=Assignee("other@flowbase.io"),
    )


def test_a_configuration_without_a_workspace_table_is_refused() -> None:
    with pytest.raises(ValueError, match="workspace"):
        _ = Settings.model_validate(
            {
                "issues": {"tracker": "linear"},
                "ticket_statuses": fake_ticket_statuses_table(),
            }
        )


def test_a_workspace_table_without_an_assignee_is_refused() -> None:
    with pytest.raises(ValueError, match=r"workspace\.assignee"):
        _ = settings_with_fake_workspace(
            issues={"tracker": "linear"}, workspace={"orca_project": "github:other/project"}
        )


def test_a_workspace_table_without_an_orca_project_is_refused() -> None:
    with pytest.raises(ValueError, match=r"workspace\.orca_project"):
        _ = settings_with_fake_workspace(
            issues={"tracker": "linear"}, workspace={"assignee": "other@flowbase.io"}
        )


def test_claims_are_labelled_workspace_unless_configured() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    assert settings.claims == ClaimSettings(label=LabelName("workspace"))


def test_a_configured_claim_label_is_read() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"}, claims={"label": "claimed"}
    )
    assert settings.claims.label == LabelName("claimed")


def test_a_configured_pool_names_its_view() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"}, pool={"view": "4efb86b38740"}
    )
    assert settings.pool == PoolSettings(view=ViewSlug("4efb86b38740"))


def test_a_pool_outside_linear_is_refused() -> None:
    with pytest.raises(ValueError, match="pool"):
        _ = settings_with_fake_workspace(
            issues={"tracker": "todoist", "project_tag": "it-mb-workflow"},
            pool={"view": "4efb86b38740"},
        )


def test_draining_without_a_pool_is_refused() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    with pytest.raises(InvalidConfigError, match=r"\[pool\] view"):
        _ = settings.required_pool()


def test_a_pool_without_limits_takes_the_default_limits() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"}, pool={"view": "4efb86b38740"}
    )
    assert settings.required_pool().limits == PoolLimits()


def test_the_pool_limits_table_sets_the_limits(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
        '[pool]\nview = "4efb86b38740"\n'
        "[pool.limits]\ntotal = 6\nQA = 2\n"
    )
    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake())
    assert resolved.settings.required_pool().limits == PoolLimits(
        total=Limit(6),
        statuses={IssueStatusName("Grilling"): Limit(1), IssueStatusName("QA"): Limit(2)},
    )


def test_a_limit_on_a_status_outside_the_chart_is_a_config_error(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
        '[pool]\nview = "4efb86b38740"\n'
        "[pool.limits]\nTodo = 1\n"
    )
    with pytest.raises(InvalidConfigError, match="Todo"):
        _ = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake())


def test_the_ticket_statuses_table_maps_each_flow_state_to_a_ticket_status(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merging = "Ready For Release"\nMerged = "Done"\n'
    )
    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake())
    assert resolved.settings.ticket_statuses.of(StateName("Merging")) == IssueStatusName(
        "Ready For Release"
    )


def test_a_ticket_statuses_table_with_a_gap_is_a_config_error_naming_the_state(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\nGrilling = "Maturing"\nSpeccing = "Maturing"\nSpecced = "Todo"\n'
        'Implementing = "In Progress"\nQA = "In Progress"\nReview = "In Review"\n'
        'Merged = "Done"\n'
    )
    with pytest.raises(InvalidConfigError, match="lacks Merging"):
        _ = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake())


def test_a_configuration_without_a_ticket_statuses_table_is_refused() -> None:
    with pytest.raises(ValueError, match="ticket_statuses"):
        _ = Settings.model_validate(
            {
                "issues": {"tracker": "linear"},
                "workspace": WorkspaceSettings.fake().model_dump(mode="json"),
            }
        )
