import tomllib

from assertions import Assert

from mb_workflow.b_core.d_domain_model.config import LinearTracker, Settings, TodoistTracker
from mb_workflow.b_core.d_domain_model.config_template import ConfigTemplate


def uncommented(template: ConfigTemplate) -> ConfigTemplate:
    return ConfigTemplate("\n".join(line.removeprefix("# ") for line in template.root.splitlines()))


def test_the_template_is_a_valid_linear_configuration() -> None:
    settings = Settings.model_validate(tomllib.loads(ConfigTemplate.default().root))
    _ = Assert.that(settings.issues).is_instance(LinearTracker)


def test_uncommenting_the_template_yields_a_valid_configuration() -> None:
    text = uncommented(ConfigTemplate.default()).root.replace(
        'tracker = "todoist"\nproject_tag = "<todoist-project-tag>"\n', ""
    )
    settings = Settings.model_validate(tomllib.loads(text))
    _ = Assert.that(settings.pool).exists()


def test_the_commented_todoist_block_is_a_valid_tracker() -> None:
    text = uncommented(ConfigTemplate.default()).root.replace(
        'tracker = "linear"\nteam = "<linear-team-key>"\nproject = "<linear-project-name>"\n', "", 1
    )
    issues = tomllib.loads(text)["issues"]
    _ = Assert.that(TodoistTracker.model_validate(issues)).is_instance(TodoistTracker)
