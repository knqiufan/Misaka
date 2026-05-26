"""Settings panel components — each module is an independent panel."""

from misaka.ui.settings.components.about_panel import AboutPanel
from misaka.ui.settings.components.appearance_panel import AppearancePanel
from misaka.ui.settings.components.env_status_panel import EnvStatusPanel
from misaka.ui.settings.components.log_viewer_panel import LogViewerPanel
from misaka.ui.settings.components.permission_panel import PermissionPanel
from misaka.ui.settings.components.router_panel import RouterPanel
from misaka.ui.settings.components.update_panel import UpdatePanel

__all__ = [
    "AboutPanel",
    "AppearancePanel",
    "EnvStatusPanel",
    "LogViewerPanel",
    "PermissionPanel",
    "RouterPanel",
    "UpdatePanel",
]
