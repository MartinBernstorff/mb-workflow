from mb_workflow.issue import IssueIdentifier
from mb_workflow.models import Value


class BranchName(Value[str]):
    @staticmethod
    def fake() -> BranchName:
        return BranchName("feat/review-workspaces")


class BranchNames(Value[tuple[BranchName, ...]]):
    @staticmethod
    def fake() -> BranchNames:
        return BranchNames((BranchName.fake(),))


class BranchSlug(Value[str]):
    @staticmethod
    def fake() -> BranchSlug:
        return BranchSlug(f"mab/{IssueIdentifier.fake().root.lower()}-feat-add-widget")


class Ref(Value[str]):
    @staticmethod
    def fake() -> Ref:
        return Ref(f"refs/heads/{BranchName.fake().root}")

    def branch(self) -> BranchName:
        return BranchName(self.root.removeprefix("refs/heads/"))
