from assertions import Assert

from mb_workflow.b_core.d_domain_model.git import BranchName, Ref


def test_ref_strips_heads_prefix() -> None:
    Assert.that(Ref.fake().branch()).matches(BranchName.fake())


def test_ref_without_prefix_is_already_a_branch() -> None:
    Assert.that(Ref("main").branch()).matches(BranchName("main"))
