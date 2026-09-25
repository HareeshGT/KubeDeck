"""AI-powered Kubernetes command operations compatibility facade.

The public API remains in this module while implementation details are split
into k8s_ai_ops_parts. Existing imports such as ``from k8s_ai_ops import
K8sAIOpsWidget, validate_action`` continue to work unchanged.
"""

from k8s_ai_ops_parts.core import *
from k8s_ai_ops_parts.ui import K8sAIOpsUIMixin
from k8s_ai_ops_parts.voice import K8sAIOpsVoiceMixin
from k8s_ai_ops_parts.operations import K8sAIOpsOperationsMixin


class K8sAIOpsWidget(
    K8sAIOpsUIMixin,
    K8sAIOpsVoiceMixin,
    K8sAIOpsOperationsMixin,
    QWidget,
):
    """Natural-language Kubernetes operations panel with persistent history."""

    operation_finished = pyqtSignal()


__all__ = [name for name in globals() if not name.startswith("__")]
