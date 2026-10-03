from mb_workflow.b_core.d_domain_model.config import (
    ConfigPath,
    Configuration,
    LinearTracker,
    NoRepoFile,
    TodoistTracker,
)
from mb_workflow.b_core.d_domain_model.config_override import (
    NoOverrideFile,
    OverrideFile,
    OverridePath,
    SettingKey,
)
from mb_workflow.d_lib.models import Value


class ReportLine(Value[str]):
    @staticmethod
    def fake() -> ReportLine:
        return ReportLine("assignee: mab@flowbase.io (repo)")

    @staticmethod
    def attributed(config: Configuration, key: SettingKey, line: ReportLine) -> ReportLine:
        sources = "+".join(source.value for source in config.sources_of(key).root)
        return ReportLine(f"{line.root} ({sources})")


class ConfigReport(Value[str]):
    @staticmethod
    def fake() -> ConfigReport:
        return ConfigReport.of(Configuration.fake())

    @staticmethod
    def of(config: Configuration) -> ConfigReport:
        settings = config.settings
        match config.origin:
            case ConfigPath() as found:
                repo = f"repo file: {found.root}"
            case NoRepoFile() as absent:
                repo = f"repo file: none (no {absent.name.root} in {absent.searched.listed().root})"
        match config.override:
            case OverrideFile() as found:
                override = f"override file: {found.path.root}"
            case NoOverrideFile(expected=OverridePath() as expected):
                override = f"override file: none (no file at {expected.root})"
            case NoOverrideFile():
                override = "override file: none (no origin remote to name it after)"
        match settings.issues:
            case TodoistTracker() as todoist:
                issues = (
                    (("issues", "tracker"), f"tracker: {todoist.tracker}"),
                    (("issues", "project_tag"), f"project tag: {todoist.project_tag.root}"),
                )
            case LinearTracker() as linear:
                issues = (
                    (("issues", "tracker"), f"tracker: {linear.tracker}"),
                    *(
                        ()
                        if linear.team is None
                        else ((("issues", "team"), f"team: {linear.team.root}"),)
                    ),
                    *(
                        ()
                        if linear.project is None
                        else ((("issues", "project"), f"project: {linear.project.root}"),)
                    ),
                )
        pool = (
            ()
            if settings.pool is None
            else (
                (("pool", "view"), f"pool view: {settings.pool.view.root}"),
                (("pool", "limits"), f"pool limits: {settings.pool.limits.summary().root}"),
                (
                    ("pool", "skip_limits_label"),
                    f"pool skip-limits label: {settings.pool.skip_limits_label.root}",
                ),
            )
        )
        attributed = (
            *issues,
            (("status", "store"), f"status store: {settings.status.store}"),
            (
                ("workspace", "orca_project"),
                f"orca project: {settings.workspace.orca_project.root}",
            ),
            (("workspace", "assignee"), f"assignee: {settings.workspace.assignee.root}"),
            (("claims", "label"), f"claim label: {settings.claims.label.root}"),
            *pool,
        )
        statuses = tuple(
            (("ticket_statuses", state.root), f"  {state.root}: {status.root}")
            for state, status in settings.ticket_statuses.root.items()
        )
        return ConfigReport(
            "\n".join(
                (
                    repo,
                    override,
                    *(
                        ReportLine.attributed(config, SettingKey(key), ReportLine(text)).root
                        for key, text in attributed
                    ),
                    "ticket statuses:",
                    *(
                        ReportLine.attributed(config, SettingKey(key), ReportLine(text)).root
                        for key, text in statuses
                    ),
                )
            )
        )
