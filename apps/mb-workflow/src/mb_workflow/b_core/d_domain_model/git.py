from mb_workflow.d_lib.models import Value


class BranchName(Value[str]):
    @staticmethod
    def fake() -> BranchName:
        return BranchName("feat/review-workspaces")


class BranchNames(Value[tuple[BranchName, ...]]):
    @staticmethod
    def fake() -> BranchNames:
        return BranchNames((BranchName.fake(),))


class Ref(Value[str]):
    @staticmethod
    def fake() -> Ref:
        return Ref(f"refs/heads/{BranchName.fake().root}")

    def branch(self) -> BranchName:
        return BranchName(self.root.removeprefix("refs/heads/"))
