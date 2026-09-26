import time
from typing import TYPE_CHECKING, override

from mb_workflow.b_core.c_secondary_ports.claims import Pause

if TYPE_CHECKING:
    from mb_workflow.b_core.d_domain_model.claim import SettleTime


class SleepingPause(Pause):
    @override
    def wait(self, duration: SettleTime) -> None:
        time.sleep(duration.root.total_seconds())
