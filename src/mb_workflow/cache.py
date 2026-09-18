from pathlib import Path

from mb_workflow.models import Value


class CacheDirectory(Value[Path]):
    @staticmethod
    def fake() -> CacheDirectory:
        return CacheDirectory.of_user()

    @staticmethod
    def of_user() -> CacheDirectory:
        return CacheDirectory(Path.home() / ".cache" / "mb-workflow")
