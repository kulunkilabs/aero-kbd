"""Small Qt worker used to keep hidraw calls off the interface thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class DeviceWorker(QRunnable):
    """Run one short hardware operation on Qt's global thread pool."""

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.operation()
        except Exception as error:  # Qt must receive hardware failures, not lose the worker.
            self.signals.failed.emit(str(error))
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
