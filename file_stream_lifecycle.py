"""Reliable lifecycle for KubeDeck remote file/preview stream workers.

The editor and preview both use FileStreamReadWorker. A worker cancelled
while Paramiko is blocked in a read/recv can otherwise remain alive while
the UI immediately starts another worker against the same transport. That
race can make the next file or preview stay on Loading indefinitely.

This module installs a small compatibility patch at application startup so
existing editor/preview call sites keep their public API unchanged.
"""

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
        """Cancel the worker and wait for its thread to fully terminate."""
        self._cancelled = True

        # Wake a blocking SFTP read / raw-channel recv where possible.
        handle = getattr(self, "_handle", None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

        # Do not let a new editor/preview reader start while this one is
        # still unwinding on the Paramiko transport.
        if self.isRunning():
            try:
                if QThread.currentThread() is not self:
                    self.wait(5000)
            except RuntimeError:
                pass

    def run(self):
        """Dispatch reads while treating cancellation as a normal stop."""
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
