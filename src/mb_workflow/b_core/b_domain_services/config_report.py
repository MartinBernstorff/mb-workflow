from mb_workflow.b_core.d_domain_model.config import Configuration, LinearTracker, TodoistTracker
from mb_workflow.d_lib.models import Value


class ConfigReport(Value[str]):
    @staticmethod
    def fake() -> ConfigReport:
        return ConfigReport.of(Configuration.fake())

    @staticmethod
    def of(config: Configuration) -> ConfigReport:
        settings = config.settings
        match settings.issues:
            case TodoistTracker() as todoist:
                issues = (
                    f"tracker: {todoist.tracker}",
                    f"project tag: {todoist.project_tag.root}",
                )
            case LinearTracker() as linear:
                issues = (f"tracker: {linear.tracker}",)
        return ConfigReport(
            "\n".join(
                (
                    *issues,
                    f"status store: {settings.status.store}",
                    f"orca project: {settings.workspace.orca_project.root}",
                    f"assignee: {settings.workspace.assignee.root}",
                    f"origin: {config.origin.root}",
                )
            )
        )
