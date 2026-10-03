from mb_workflow.b_core.d_domain_model.workspace import ProjectSelector


def test_a_mixed_case_project_selector_is_lowercased() -> None:
    mixed_case = "github:MartinBernstorff/codetaster"
    lowercase = "github:martinbernstorff/codetaster"
    assert ProjectSelector(mixed_case).root == lowercase
