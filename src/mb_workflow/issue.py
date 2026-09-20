from mb_workflow.models import Value


class IssueIdentifier(Value[str]):
    @staticmethod
    def fake() -> IssueIdentifier:
        return IssueIdentifier("E-4289")


class PrNumber(Value[int]):
    @staticmethod
    def fake() -> PrNumber:
        return PrNumber(1234)


class PrTitle(Value[str]):
    @staticmethod
    def fake() -> PrTitle:
        return PrTitle("Add review workspaces")
