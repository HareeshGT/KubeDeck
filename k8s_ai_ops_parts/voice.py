from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QMessageBox,
    QShortcut,
    QProgressBar,
    QComboBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QGraphicsBlurEffect

from ui_icons import set_icon, apply_text_icon, icon_button
from themes import T, load_settings, save_settings
from utils import monospace_font
from .core import *
from .core import _NarrationThread, _TTS_AVAILABLE, _VOICE_AVAILABLE


class K8sAIOpsVoiceMixin:
    def _toggle_voice_feedback(self, checked: bool):
        self._voice_feedback_enabled = checked and _TTS_AVAILABLE
        apply_text_icon(self.speaker_btn, ' Speak' if self._voice_feedback_enabled else ' Speak', size=15)
        save_voice_feedback_enabled(self._voice_feedback_enabled)
        if not self._voice_feedback_enabled and self._narrator is not None:
            self._narrator.stop()
            self._narrator = None

    def _populate_voice_combo(self):
        """Fill the voice picker from the system's installed TTS voices,
        selecting whichever one is currently persisted. Falls back to
        "System Default" if nothing is persisted, or if a persisted voice
        id no longer matches an installed voice (e.g. settings carried
        over from a different machine)."""
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        self.voice_combo.addItem('System Default', '')
        for voice in list_voices():
            self.voice_combo.addItem(voice['name'], voice['id'])
        idx = self.voice_combo.findData(self._voice_id)
        self.voice_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.voice_combo.blockSignals(False)

    def _on_voice_combo_changed(self, index: int):
        voice_id = self.voice_combo.itemData(index) or ''
        if voice_id == self._voice_id:
            return
        self._voice_id = voice_id
        save_voice_id(voice_id)
        if self._narrator is not None:
            self._narrator.stop()
            self._narrator = None

    def _speak(self, text: str):
        """Queue `text` to be spoken aloud, if narration is available and
        currently enabled. Safe to call from any point in the flow — a
        disabled/unavailable narrator just drops the phrase."""
        if not self._voice_feedback_enabled or not _TTS_AVAILABLE:
            return
        if self._narrator is None:
            self._narrator = _NarrationThread(voice_id=self._voice_id, parent=self)
            self._narrator.start()
        self._narrator.speak(text)

    def _toggle_voice_recording(self):
        """Start/stop microphone capture without using an LLM for STT."""
        if not self._ai_access_allowed:
            self.refresh_ai_access()
            return
        if self._voice_recording:
            self._stop_voice_recording()
            return
        if self._busy:
            return
        if not _VOICE_AVAILABLE:
            QMessageBox.information(self, 'Voice Input Unavailable', 'Install the voice-input dependencies first:\n\npython3 -m pip install SpeechRecognition PyAudio\n\nOn macOS, install PortAudio first if PyAudio cannot build:\nbrew install portaudio')
            return
        if self._ai_worker is not None or self._operation_worker is not None:
            self._write_info('\nPlease wait for the current AI/Kubernetes operation to finish.')
            return
        self._start_voice_recording()

    def _start_voice_recording(self):
        if self._voice_worker is not None:
            return
        self._voice_recording = True
        self.voice_btn.setText('⏹ Stop Voice')
        self.voice_btn.setToolTip('Stop recording and send the transcription to Ops Mind')
        self.request_input.clear()
        self.request_input.setPlaceholderText('Listening… speak your Kubernetes command')
        self.request_input.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.clear_history_btn.setEnabled(False)
        self.status_lbl.setText('Listening…')
        self._write_info('\n Listening… say a Kubernetes operation, then press Stop Voice or Ctrl+Shift+Space.')
        worker = K8sGoogleSpeechWorker(language=GOOGLE_STT_LANGUAGE, max_seconds=VOICE_MAX_SECONDS)
        worker.listening.connect(self._on_voice_listening)
        worker.stopped.connect(self._on_voice_stopped)
        worker.level.connect(self._on_voice_level)
        worker.done.connect(self._on_voice_done)
        worker.error.connect(self._on_voice_error)
        worker.finished.connect(self._on_voice_finished)
        self._voice_worker = worker
        track_worker(self._workers, worker)
        worker.start()

    def _stop_voice_recording(self):
        worker = self._voice_worker
        if worker is None:
            return
        self.status_lbl.setText('Transcribing…')
        self.voice_btn.setText('⌛ Transcribing…')
        self.voice_btn.setEnabled(False)
        worker.stop()

    def _on_voice_level(self, level: int):
        """Update the live microphone meter."""
        if not hasattr(self, 'mic_level_bar'):
            return
        level = max(0, min(100, int(level)))
        self.mic_level_bar.setValue(level)
        if level >= 75:
            self.mic_level_label.setText('Mic • high')
        elif level >= 35:
            self.mic_level_label.setText('Mic • medium')
        elif level >= 5:
            self.mic_level_label.setText('Mic • low')
        else:
            self.mic_level_label.setText('Mic')

    def _on_voice_listening(self):
        if self._voice_recording:
            self.status_lbl.setText('Listening…')

    def _on_voice_stopped(self):
        if self._voice_recording:
            self.status_lbl.setText('Transcribing…')

    def _on_voice_done(self, text: str):
        text = (text or '').strip()
        if not text:
            self._on_voice_error('The voice transcription was empty.')
            return
        self.request_input.setPlaceholderText('Ask AI to perform a Kubernetes operation…')
        self.request_input.setText(text)
        self._write_info(f'\n You said: "{self._escape_html(text)}"')
        self._voice_recording = False
        self.voice_btn.setEnabled(True)
        apply_text_icon(self.voice_btn, ' Voice', size=15)
        self.voice_btn.setToolTip('Start/stop voice command. Hotkey: Ctrl+Shift+Space')
        self.request_input.setEnabled(True)
        self._submit()

    def _on_voice_error(self, message: str):
        self._write_error('\n Voice input error:\n' + str(message))
        self._voice_recording = False
        self.request_input.setPlaceholderText('Ask AI to perform a Kubernetes operation…')
        self.request_input.setEnabled(not self._busy)
        self.voice_btn.setEnabled(not self._busy)
        apply_text_icon(self.voice_btn, ' Voice', size=15)
        self.voice_btn.setToolTip('Start/stop voice command. Hotkey: Ctrl+Shift+Space')
        self.status_lbl.setText('Ready')

    def _on_voice_finished(self):
        self._voice_worker = None
        if self._voice_recording:
            self._voice_recording = False
        self.voice_btn.setEnabled(not self._busy)
        apply_text_icon(self.voice_btn, ' Voice', size=15)
        self.voice_btn.setToolTip('Start/stop voice command. Hotkey: Ctrl+Shift+Space')
        self.request_input.setPlaceholderText('Ask AI to perform a Kubernetes operation…')
        self.request_input.setEnabled(not self._busy)
        if hasattr(self, 'mic_level_bar'):
            self.mic_level_bar.setValue(0)
        if hasattr(self, 'mic_level_label'):
            self.mic_level_label.setText('Mic')
        if not self._busy:
            self.status_lbl.setText('Ready')
