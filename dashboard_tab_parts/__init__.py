"""Lazy public exports for dashboard_tab mixins.

The mixin modules import shared names from the dashboard facade, so eager
imports here would create a dashboard_tab <-> dashboard_tab_parts cycle.
Keep these exports lazy to preserve the existing public API without the cycle.
"""

__all__ = [
    "DashboardConnectionMixin",
    "DashboardUIMixin",
    "DashboardRefreshMixin",
    "DashboardNodesHistoryMixin",
]


def __getattr__(name):
    if name == "DashboardConnectionMixin":
        from .connection import DashboardConnectionMixin
        return DashboardConnectionMixin

    if name == "DashboardUIMixin":
        from .ui import DashboardUIMixin
        return DashboardUIMixin

    if name == "DashboardRefreshMixin":
        from .refresh import DashboardRefreshMixin
        return DashboardRefreshMixin

    if name == "DashboardNodesHistoryMixin":
        from .nodes_history import DashboardNodesHistoryMixin
        return DashboardNodesHistoryMixin

    raise AttributeError(name)