from mb_workflow.b_core.d_domain_model.config import ClaimSettings, OrcaStatus
from mb_workflow.b_core.d_domain_model.flow import WorkflowChart
from mb_workflow.b_core.d_domain_model.pool import PoolLimits
from mb_workflow.d_lib.models import Value


class ConfigTemplate(Value[str]):
    @staticmethod
    def fake() -> ConfigTemplate:
        return ConfigTemplate.default()

    @staticmethod
    def default() -> ConfigTemplate:
        limits = PoolLimits()
        return ConfigTemplate(
            "\n".join(
                (
                    "[issues]",
                    'tracker = "linear"',
                    '# tracker = "todoist"',
                    '# project_tag = "<todoist-project-tag>"',
                    "",
                    "[workspace]",
                    'orca_project = "github:<owner>/<repo>"',
                    'assignee = "<you@example.com>"',
                    "",
                    "# [pool]",
                    '# view = "<linear-view-slug>"',
                    "",
                    "# [pool.limits]",
                    f"# total = {limits.total.root}",
                    *(f"# {state.root} = {limit.root}" for state, limit in limits.states.items()),
                    "",
                    "# [claims]",
                    f'# label = "{ClaimSettings().label.root}"',
                    "",
                    "# [status]",
                    f'# store = "{OrcaStatus().store.value}"',
                    "",
                    "[ticket_statuses]",
                    *(f'{state.name} = "{state.name}"' for state in WorkflowChart.states),
                    "",
                )
            )
        )
