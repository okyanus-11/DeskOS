"""Individual Control Center pages."""

from deskos.control_center.pages.appearance import AppearancePage
from deskos.control_center.pages.applications import ApplicationsPage
from deskos.control_center.pages.general import GeneralPage
from deskos.control_center.pages.network import NetworkPage
from deskos.control_center.pages.plugins import PluginsPage
from deskos.control_center.pages.system import SystemPage

__all__ = [
    "AppearancePage",
    "ApplicationsPage",
    "GeneralPage",
    "NetworkPage",
    "PluginsPage",
    "SystemPage",
]
