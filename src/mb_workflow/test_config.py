from pathlib import Path

import pytest

from mb_workflow.config import (
    ConfigFileName,
    Configuration,
    InvalidConfigError,
    LinearTracker,
    MissingConfigError,
    OrcaStatus,
    ProjectTag,
    SearchedDirectories,
    Settings,
    StatusStore,
    TodoistTracker,
    Tracker,
    WorkingDirectory,
)


def test_the_search_starts_at_the_working_directory_and_walks_up() -> None:
    searched = SearchedDirectories.of(WorkingDirectory(Path("/a/b/c")))
    assert searched.root == (Path("/a/b/c"), Path("/a/b"), Path("/a"), Path("/"))


def test_the_nearest_configuration_file_wins(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text('[issues]\ntracker = "linear"\n')
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-mb-workflow"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.origin.root == tmp_path / "repo" / "src" / "mb-workflow.toml"
    assert resolved.settings.issues == TodoistTracker.fake()


def test_the_search_walks_up_when_the_working_directory_holds_no_file(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text('[issues]\ntracker = "linear"\n')

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.origin.root == tmp_path / "repo" / "mb-workflow.toml"


def test_a_configuration_in_a_parent_is_not_merged_into_the_nearest_one(tmp_path: Path) -> None:
    (tmp_path / "repo" / "src").mkdir(parents=True)
    _ = (tmp_path / "repo" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "todoist"\nproject_tag = "it-other-project"\n'
    )
    _ = (tmp_path / "repo" / "src" / "mb-workflow.toml").write_text(
        '[issues]\ntracker = "linear"\n'
    )

    resolved = Configuration.resolved(
        WorkingDirectory(tmp_path / "repo" / "src"), ConfigFileName.fake()
    )

    assert resolved.settings == Settings(issues=LinearTracker.fake())


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
    settings = Settings.model_validate({"issues": {"tracker": "linear"}})
    assert settings.issues == LinearTracker(tracker=Tracker.linear)


def test_a_todoist_configuration_names_its_project_tag() -> None:
    settings = Settings.model_validate(
        {"issues": {"tracker": "todoist", "project_tag": "it-mb-workflow"}}
    )
    assert settings.issues == TodoistTracker(tracker=Tracker.todoist, project_tag=ProjectTag.fake())


def test_a_todoist_configuration_without_a_project_tag_is_refused() -> None:
    with pytest.raises(ValueError, match=r"todoist\.project_tag"):
        _ = Settings.model_validate({"issues": {"tracker": "todoist"}})


def test_a_project_tag_without_todoist_is_refused() -> None:
    with pytest.raises(ValueError, match=r"linear\.project_tag"):
        _ = Settings.model_validate(
            {"issues": {"tracker": "linear", "project_tag": "it-mb-workflow"}}
        )


def test_an_unknown_tracker_is_refused() -> None:
    with pytest.raises(ValueError, match="union_tag_invalid"):
        _ = Settings.model_validate({"issues": {"tracker": "jira"}})


def test_a_configuration_naming_no_tracker_is_refused() -> None:
    with pytest.raises(ValueError, match="issues"):
        _ = Settings.model_validate({})


def test_the_status_store_defaults_to_orca() -> None:
    settings = Settings.model_validate({"issues": {"tracker": "linear"}})
    assert settings.status == OrcaStatus(store=StatusStore.orca)


def test_the_status_store_can_be_named_explicitly() -> None:
    settings = Settings.model_validate(
        {"issues": {"tracker": "linear"}, "status": {"store": "orca"}}
    )
    assert settings.status == OrcaStatus.fake()


def test_an_unknown_status_store_is_refused() -> None:
    with pytest.raises(ValueError, match="union_tag_invalid"):
        _ = Settings.model_validate(
            {"issues": {"tracker": "linear"}, "status": {"store": "sticky-notes"}}
        )


def test_a_setting_the_file_does_not_define_is_refused() -> None:
    with pytest.raises(ValueError, match="extra_forbidden"):
        _ = Settings.model_validate({"issues": {"tracker": "linear"}, "sttaus": {"store": "orca"}})
