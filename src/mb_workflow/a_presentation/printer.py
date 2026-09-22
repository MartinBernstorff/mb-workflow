import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mb_workflow.b_core.c_secondary_ports.printer import PrintedText


class StdoutPrinter:
    def write(self, text: PrintedText) -> None:
        _ = sys.stdout.write(text.root)
