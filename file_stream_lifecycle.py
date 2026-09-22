"""Reliable lifecycle for KubeDeck remote file/preview stream workers."""

from PyQt5 import sip
from PyQt5.QtCore import QThread

_PATCHED = False


def install():
    """Patch FileStreamReadWorker once, before any instances are created."""
    global _PATCHED
    if _PATCHED:
        return

    from workers import FileStreamReadWorker

    if getattr(FileStreamReadWorker, "_kdb_lifecycle_patch", False):
        _PATCHED = True
        return

    def cancel(self):
        """Cancel safely, including when Qt has already deleted the wrapper."""
        try:
            if sip.isdeleted(self):
                return
        except Exception:
            return

        self._cancelled = True

        handle = getattr(self, "_handle", None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

        try:
            running = self.isRunning()
        except RuntimeError:
            return

        if running:
            try:
                if QThread.currentThread() is not self:
                    self.wait(5000)
            except RuntimeError:
                pass

    def run(self):
        try:
            if hasattr(self._sftp, "_ftp"):
                self._run_ftp_stream()
            elif self._sudo_user:
                self._run_sudo_stream()
            else:
                self._run_direct_stream()
        except Exception as exc:
            if not getattr(self, "_cancelled", False):
                self.finished_err.emit(str(exc))

    FileStreamReadWorker.cancel = cancel
    FileStreamReadWorker.run = run
    FileStreamReadWorker._kdb_lifecycle_patch = True
    _PATCHED = True
