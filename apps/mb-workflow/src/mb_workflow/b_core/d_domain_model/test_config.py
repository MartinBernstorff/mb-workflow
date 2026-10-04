from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from assertions import Assert

from mb_workflow.b_core.d_domain_model.config import (
    ClaimSettings,
    ConfigFileName,
    ConfigPath,
    Configuration,
    InvalidConfigError,
    LinearTracker,
    MissingConfigError,
    NoRepoFile,
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
from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingsTable,
)
from mb_workflow.b_core.d_domain_model.flow import StateName
from mb_workflow.b_core.d_domain_model.issue import (
    Assignee,
    IssueStatusName,
    LabelName,
    ProjectName,
    TeamKey,
)
from mb_workflow.b_core.d_domain_model.pool import Limit, PoolLimits, ViewSlug
from mb_workflow.b_core.d_domain_model.ticket_draft import TicketDefaults
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
    Assert.that(searched.root).matches((Path("/a/b/c"), Path("/a/b"), Path("/a"), Path("/")))


def test_a_configuration_in_the_working_directory_of_a_repository_is_found(
    tmp_path: Path,
) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text("")

    located = SearchedDirectories.of(WorkingDirectory(tmp_path / "repo")).find(
        ConfigFileName.fake()
    )

    Assert.that(located).matches(ConfigPath((tmp_path / "repo" / "mb-workflow.toml").resolve()))


def test_a_configuration_in_a_parent_within_the_repository_is_found(tmp_path: Path) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "src" / "pkg").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text("")

    located = SearchedDirectories.of(WorkingDirectory(tmp_path / "repo" / "src" / "pkg")).find(
        ConfigFileName.fake()
    )

    Assert.that(located).matches(ConfigPath((tmp_path / "repo" / "mb-workflow.toml").resolve()))


def test_a_configuration_above_the_repository_root_is_not_found(tmp_path: Path) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "src").mkdir()
    _ = (tmp_path / "mb-workflow.toml").write_text("")

    searched = SearchedDirectories.of(WorkingDirectory(tmp_path / "repo" / "src"))

    Assert.that(searched.find(ConfigFileName.fake())).matches(None)
    Assert.that(searched.root).matches(
        ((tmp_path / "repo" / "src").resolve(), (tmp_path / "repo").resolve())
    )


def test_a_worktree_git_file_marks_the_repository_root(tmp_path: Path) -> None:
    (tmp_path / "worktree" / "src").mkdir(parents=True)
    _ = (tmp_path / "worktree" / ".git").write_text("gitdir: /elsewhere/.git/worktrees/worktree\n")

    searched = SearchedDirectories.of(WorkingDirectory(tmp_path / "worktree" / "src"))

    Assert.that(searched.root).matches(
        (
            (tmp_path / "worktree" / "src").resolve(),
            (tmp_path / "worktree").resolve(),
        )
    )


def test_the_nearest_configuration_file_wins(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake(), NoOverrideFile.fake()
    ).unwrap()

    Assert.that(resolved.origin).matches(ConfigPath(tmp_path / "repo" / "src" / "mb-workflow.toml"))
    Assert.that(resolved.settings.issues).matches(TodoistTracker.fake())


def test_the_search_walks_up_when_the_working_directory_holds_no_file(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake(), NoOverrideFile.fake()
    ).unwrap()

    Assert.that(resolved.origin).matches(ConfigPath(tmp_path / "repo" / "mb-workflow.toml"))


def test_a_configuration_in_a_parent_is_not_merged_into_the_nearest_one(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-other-project"\n'
        '[workspace]\norca_project = "github:other/project"\nassignee = "other@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake(), NoOverrideFile.fake()
    ).unwrap()

    Assert.that(resolved.settings).matches(
        Settings(
            issues=LinearTracker(tracker=TicketTracker.linear),
            workspace=WorkspaceSettings.fake(),
            ticket_statuses=TicketStatuses.fake(),
        )
    )


def test_without_either_file_the_error_names_the_directories_searched_and_the_override_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    expected = OverridePath(tmp_path / "override.toml")

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo"),
        ConfigFileName("absent.toml"),
        NoOverrideFile(expected=expected),
    )

    error = Assert.that(resolved.error).is_instance(MissingConfigError)
    Assert.that(str(error)).contains("absent.toml")
    Assert.that(str(error)).contains(str((tmp_path / "repo").resolve()))
    Assert.that(str(error)).contains(str(expected.root))


def test_without_either_file_or_an_origin_remote_the_error_says_so(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile(expected=None)
    )

    error = Assert.that(resolved.error).exists()
    Assert.that(str(error)).contains("no origin remote")


def test_an_override_file_alone_resolves_the_configuration(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    override = OverrideFile(path=OverridePath.fake(), table=Configuration.fake().table)

    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    Assert.that(resolved.unwrap().settings).matches(Settings.fake())
    Assert.that(resolved.unwrap().origin).matches(
        NoRepoFile(name=ConfigFileName.fake(), searched=SearchedDirectories((tmp_path.resolve(),)))
    )


def test_an_invalid_override_file_alone_is_an_error_naming_it(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    override = OverrideFile(
        path=OverridePath.fake(), table=SettingsTable({"issues": {"tracker": "jira"}})
    )

    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    error = Assert.that(resolved.error).is_instance(InvalidConfigError)
    Assert.that(str(error)).contains(str(OverridePath.fake().root))


def test_a_malformed_configuration_file_names_itself(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text('[issues]\ntracker = "jira"\n')
    with pytest.raises(InvalidConfigError) as raised:
        _ = Configuration.resolved(
            WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake()
        ).unwrap()
    Assert.that(str(raised.value)).contains(str(tmp_path / "mb-workflow.toml"))


def test_a_linear_configuration_names_only_its_tracker() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    Assert.that(settings.issues).matches(LinearTracker(tracker=TicketTracker.linear))


def test_a_linear_configuration_without_a_team_or_project_creates_tickets_without_defaults() -> (
    None
):
    settings = settings_with_fake_workspace(issues={"tracker": "linear"})
    Assert.that(settings.ticket_defaults()).matches(TicketDefaults(team=None, project=None))


def test_a_linear_configuration_names_the_team_and_project_tickets_are_created_in() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear", "team": "MB", "project": "mb-workflow"}
    )
    Assert.that(settings.ticket_defaults()).matches(
        TicketDefaults(team=TeamKey("MB"), project=ProjectName("mb-workflow"))
    )


def test_creating_a_ticket_outside_linear_is_refused() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "todoist", "project_tag": "it-mb-workflow"}
    )
    with pytest.raises(InvalidConfigError, match="linear"):
        _ = settings.ticket_defaults()


def test_a_todoist_configuration_names_its_project_tag() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "todoist", "project_tag": "it-mb-workflow"}
    )
    Assert.that(settings.issues).matches(
        TodoistTracker(tracker=TicketTracker.todoist, project_tag=ProjectTag.fake())
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
    Assert.that(settings.status).matches(OrcaStatus(store=StatusStore.orca))


def test_an_empty_status_table_defaults_to_orca() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"}, status={})
    Assert.that(settings.status).matches(OrcaStatus.fake())


def test_the_status_store_can_be_named_explicitly() -> None:
    settings = settings_with_fake_workspace(issues={"tracker": "linear"}, status={"store": "orca"})
    Assert.that(settings.status).matches(OrcaStatus.fake())


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
    Assert.that(settings.workspace).matches(
        WorkspaceSettings(
            orca_project=ProjectSelector("github:other/project"),
            assignee=Assignee("other@flowbase.io"),
        )
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
    Assert.that(settings.claims).matches(ClaimSettings(label=LabelName("workspace")))


def test_a_configured_claim_label_is_read() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"}, claims={"label": "claimed"}
    )
    Assert.that(settings.claims.label).matches(LabelName("claimed"))


def test_a_configured_pool_names_its_view() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"}, pool={"view": "4efb86b38740"}
    )
    Assert.that(settings.pool).matches(PoolSettings(view=ViewSlug("4efb86b38740")))


def test_a_configured_skip_limits_label_is_read() -> None:
    settings = settings_with_fake_workspace(
        issues={"tracker": "linear"},
        pool={"view": "4efb86b38740", "skip_limits_label": "expedite"},
    )
    Assert.that(settings.required_pool().skip_limits_label).matches(LabelName("expedite"))


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
    Assert.that(settings.required_pool().limits).matches(PoolLimits())


def test_the_pool_limits_table_sets_the_limits(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
        '[pool]\nview = "4efb86b38740"\n'
        "[pool.limits]\ntotal = 6\n[pool.limits.states]\nQA = 2\n[pool.limits.labels]\nrefactor = 1\n"
    )
    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake()
    ).unwrap()
    Assert.that(resolved.settings.required_pool().limits).matches(
        PoolLimits(
            total=Limit(6),
            states={StateName("grill"): Limit(1), StateName("qa"): Limit(2)},
            labels={LabelName("refactor"): Limit(1)},
        )
    )


def test_a_limit_on_a_state_outside_the_chart_is_a_config_error(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
        '[pool]\nview = "4efb86b38740"\n'
        "[pool.limits.states]\nSpecced = 1\n"
    )
    with pytest.raises(InvalidConfigError, match="Specced"):
        _ = Configuration.resolved(
            WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake()
        ).unwrap()


def test_the_ticket_statuses_table_maps_each_flow_state_to_a_ticket_status(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake()
    ).unwrap()
    Assert.that(resolved.settings.ticket_statuses.of(StateName("merging"))).matches(
        IssueStatusName("Ready For Release")
    )


def test_a_ticket_statuses_table_with_a_gap_is_a_config_error_naming_the_state(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merged = "Done"\n'
    )
    with pytest.raises(InvalidConfigError, match="lacks merging"):
        _ = Configuration.resolved(
            WorkingDirectory(tmp_path), ConfigFileName.fake(), NoOverrideFile.fake()
        ).unwrap()


def test_a_configuration_without_a_ticket_statuses_table_is_refused() -> None:
    with pytest.raises(ValueError, match="ticket_statuses"):
        _ = Settings.model_validate(
            {
                "issues": {"tracker": "linear"},
                "workspace": WorkspaceSettings.fake().model_dump(mode="json"),
            }
        )


def test_an_override_file_sets_one_nested_key_and_keeps_its_siblings(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    override = OverrideFile(
        path=OverridePath.fake(),
        table=SettingsTable({"workspace": {"assignee": "me@example.com"}}),
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path), ConfigFileName.fake(), override
    ).unwrap()

    Assert.that(resolved.settings.workspace).matches(
        WorkspaceSettings(
            orca_project=WorkspaceSettings.fake().orca_project, assignee=Assignee("me@example.com")
        )
    )


def test_an_override_making_the_configuration_invalid_is_an_error_naming_both_files(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    override = OverrideFile(
        path=OverridePath.fake(), table=SettingsTable({"workspace": {"assigne": "typo"}})
    )

    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    error = Assert.that(resolved.error).is_instance(InvalidConfigError)
    Assert.that(str(error)).contains(str(tmp_path / "mb-workflow.toml"))
    Assert.that(str(error)).contains(str(OverridePath.fake().root))


def test_an_override_may_supply_a_setting_the_repository_file_lacks(tmp_path: Path) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
    )
    override = OverrideFile(
        path=OverridePath.fake(), table=SettingsTable({"workspace": {"assignee": "me@example.com"}})
    )

    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    Assert.that(resolved.unwrap().settings.workspace.assignee).matches(Assignee("me@example.com"))


def test_an_override_state_limit_in_another_casing_limits_the_chart_state(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
        '[workspace]\norca_project = "github:flowbasedk/flowbase"\nassignee = "mab@flowbase.io"\n'
        '[ticket_statuses]\ngrill = "Maturing"\nto-ticket = "Maturing"\ntodo = "Todo"\n'
        'implementing = "In Progress"\nqa = "In Progress"\nreview = "In Review"\n'
        'merging = "Ready For Release"\nmerged = "Done"\n'
        '[pool]\nview = "4efb86b38740"\n'
        "[pool.limits.states]\nQA = 2\n"
    )
    state, mine = StateName("qa"), 3
    override = OverrideFile(
        path=OverridePath.fake(),
        table=SettingsTable({"pool": {"limits": {"states": {state.root.lower(): mine}}}}),
    )

    resolved = Configuration.resolved(WorkingDirectory(tmp_path), ConfigFileName.fake(), override)

    Assert.that(resolved.unwrap().settings.required_pool().limits.states[state]).matches(
        Limit(mine)
    )
