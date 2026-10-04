from assertions import Assert

from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingKey,
    SettingSource,
    SettingSources,
    SettingsTable,
)


def test_an_override_replaces_a_top_level_key() -> None:
    merged = SettingsTable({"name": "repo", "kept": 1}).merged(SettingsTable({"name": "mine"}))
    Assert.that(merged).matches(SettingsTable({"name": "mine", "kept": 1}))


def test_an_override_of_a_nested_key_leaves_its_siblings_intact() -> None:
    repo = SettingsTable(
        {"workspace": {"orca_project": "github:a/b", "assignee": "repo@example.com"}}
    )
    merged = repo.merged(SettingsTable({"workspace": {"assignee": "me@example.com"}}))
    Assert.that(merged).matches(
        SettingsTable({"workspace": {"orca_project": "github:a/b", "assignee": "me@example.com"}})
    )


def test_an_override_merges_tables_at_every_depth() -> None:
    repo = SettingsTable({"pool": {"limits": {"total": 4, "states": {"QA": 1}}}})
    merged = repo.merged(SettingsTable({"pool": {"limits": {"states": {"Review": 2}}}}))
    Assert.that(merged).matches(
        SettingsTable({"pool": {"limits": {"total": 4, "states": {"QA": 1, "Review": 2}}}})
    )


def test_an_override_key_replaces_the_repo_key_whatever_its_casing() -> None:
    mine = SettingsTable({"qa": 3})
    Assert.that(SettingsTable({"QA": 2}).merged(mine)).matches(mine)


def test_keys_differing_in_casing_within_the_override_are_both_kept() -> None:
    mine = {"QA": 1, "qa": 2}
    merged = SettingsTable({"QA": 3}).merged(SettingsTable(mine))
    Assert.that(merged).matches(SettingsTable(mine))


def test_a_table_may_replace_a_value_of_another_shape() -> None:
    merged = SettingsTable({"pool": "none"}).merged(SettingsTable({"pool": {"view": "x"}}))
    Assert.that(merged).matches(SettingsTable({"pool": {"view": "x"}}))


def test_an_absent_key_has_no_entry() -> None:
    Assert.that(SettingsTable.fake().entry(SettingKey(("workspace", "orca_project")))).matches(None)


def test_a_setting_without_an_override_file_comes_from_the_repo() -> None:
    sources = SettingSources.of(SettingKey.fake(), SettingsTable.fake(), NoOverrideFile.fake())
    Assert.that(sources).matches(SettingSources((SettingSource.repo,)))


def test_an_overridden_value_comes_from_the_override_alone() -> None:
    sources = SettingSources.of(SettingKey.fake(), SettingsTable.fake(), OverrideFile.fake())
    Assert.that(sources).matches(SettingSources((SettingSource.override,)))


def test_a_setting_in_neither_file_is_a_default() -> None:
    override = OverrideFile(path=OverridePath.fake(), table=SettingsTable.empty())
    sources = SettingSources.of(SettingKey(("claims", "label")), SettingsTable.empty(), override)
    Assert.that(sources).matches(SettingSources((SettingSource.default,)))
