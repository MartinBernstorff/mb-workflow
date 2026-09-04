from mb_workflow.models import Value


class BranchName(Value[str]):
    @staticmethod
    def fake() -> BranchName:
        return BranchName("feat/review-workspaces")


class Ref(Value[str]):
    @staticmethod
    def fake() -> Ref:
        return Ref(f"refs/heads/{BranchName.fake().root}")

    def branch(self) -> BranchName:
        return BranchName(self.root.removeprefix("refs/heads/"))
