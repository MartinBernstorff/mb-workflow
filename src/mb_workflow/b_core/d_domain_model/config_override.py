from enum import StrEnum
from pathlib import Path

from pydantic import JsonValue

from mb_workflow.d_lib.models import Model, Value


class InvalidOverrideError(Exception):
    pass


class SettingKey(Value[tuple[str, ...]]):
    @staticmethod
    def fake() -> SettingKey:
        return SettingKey(("workspace", "assignee"))


class SettingEntry(Value[JsonValue]):
    @staticmethod
    def fake() -> SettingEntry:
        return SettingEntry("mab@flowbase.io")

    def is_table(self) -> IsTable:
        return IsTable(isinstance(self.root, dict))


class IsTable(Value[bool]):
    @staticmethod
    def fake() -> IsTable:
        return IsTable(False)


class SettingsTable(Value[dict[str, JsonValue]]):
    @staticmethod
    def fake() -> SettingsTable:
        return SettingsTable({"workspace": {"assignee": SettingEntry.fake().root}})

    @staticmethod
    def empty() -> SettingsTable:
        return SettingsTable({})

    # An override key replaces the repo key it matches ignoring case, so `qa` overrides `QA`.
    def merged(self, override: SettingsTable) -> SettingsTable:
        override_spelling = {
            repo_key: override_key
            for override_key in override.root
            for repo_key in self.root
            if repo_key.casefold() == override_key.casefold()
        }
        merged = {
            override_spelling.get(repo_key, repo_key): value
            for repo_key, value in self.root.items()
        }
        for key, value in override.root.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = SettingsTable(current).merged(SettingsTable(value)).root
            else:
                merged[key] = value
        return SettingsTable(merged)

    def entry(self, key: SettingKey) -> SettingEntry | None:
        current: JsonValue = self.root
        for part in key.root:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return SettingEntry(current)


class OverridePath(Value[Path]):
    @staticmethod
    def fake() -> OverridePath:
        return OverridePath(
            Path("/Users/me/.config/mb-workflow/projects/MartinBernstorff/mb-workflow.toml")
        )


class OverrideFile(Model):
    path: OverridePath
    table: SettingsTable

    @staticmethod
    def fake() -> OverrideFile:
        return OverrideFile(path=OverridePath.fake(), table=SettingsTable.fake())


# Expected is None when the repository has no origin remote to name its override file after.
class NoOverrideFile(Model):
    expected: OverridePath | None

    @staticmethod
    def fake() -> NoOverrideFile:
        return NoOverrideFile(expected=OverridePath.fake())


type ProjectOverride = OverrideFile | NoOverrideFile


class SettingSource(StrEnum):
    repo = "repo"
    override = "override"
    default = "default"


class SettingSources(Value[tuple[SettingSource, ...]]):
    @staticmethod
    def fake() -> SettingSources:
        return SettingSources((SettingSource.repo,))

    @staticmethod
    def of(key: SettingKey, repo: SettingsTable, override: ProjectOverride) -> SettingSources:
        overriding = override.table.entry(key) if isinstance(override, OverrideFile) else None
        if overriding is not None and not overriding.is_table().root:
            return SettingSources((SettingSource.override,))
        held = tuple(
            source
            for source, entry in (
                (SettingSource.repo, repo.entry(key)),
                (SettingSource.override, overriding),
            )
            if entry is not None
        )
        return SettingSources(held or (SettingSource.default,))
