"""Background automation (worker thread) for Idle Champions."""

from ic_automation.controller import AutomationController
from ic_automation.settings import AutomationSettings
from ic_automation.worker import StatusEvent

__all__ = [
    "AutomationController",
    "AutomationSettings",
    "StatusEvent",
]
