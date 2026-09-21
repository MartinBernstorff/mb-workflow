from mb_workflow.b_core.git import BranchName, Ref


def test_ref_strips_heads_prefix() -> None:
    assert Ref.fake().branch() == BranchName.fake()


def test_ref_without_prefix_is_already_a_branch() -> None:
    assert Ref("main").branch() == BranchName("main")
