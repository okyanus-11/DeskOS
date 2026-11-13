"""DeskSettings — DeskOS's unified configuration interface.

The implementation lives in :mod:`deskos.control_center` because the same UI is
used both as a standalone window ("DeskSettings") and as the Control Center
opened from the dock.
"""

from deskos.control_center.window import ControlCenterWindow

__all__ = ["ControlCenterWindow"]
