from mb_workflow.d_lib.models import Value


class Failed(Value[bool]):
    @staticmethod
    def fake() -> Failed:
        return Failed(False)
