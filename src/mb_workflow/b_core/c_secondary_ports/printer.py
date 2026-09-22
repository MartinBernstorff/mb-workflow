from typing import Protocol

from mb_workflow.d_lib.models import Value


class PrintedText(Value[str]):
    @staticmethod
    def fake() -> PrintedText:
        return PrintedText("Grilling\n")


class Printer(Protocol):
    def write(self, text: PrintedText) -> None: ...


class FakePrinter:
    def __init__(self) -> None:
        self._written: list[PrintedText] = []

    def write(self, text: PrintedText) -> None:
        self._written.append(text)

    def written(self) -> PrintedText:
        return PrintedText("".join(text.root for text in self._written))
