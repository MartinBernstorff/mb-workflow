from mb_workflow.d_lib.models import Value


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class BranchSlug(Value[str]):
    @staticmethod
    def fake() -> BranchSlug:
        return BranchSlug(f"mab/{IssueIdentifier.fake().root.lower()}-feat-add-widget")
