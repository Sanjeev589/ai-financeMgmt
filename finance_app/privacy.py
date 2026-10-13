"""Deny network and external-process activity for the application lifetime."""

import sys

_enabled = False


def _deny_external_activity(event, args):
    if event.startswith(("socket.", "http.client.", "urllib.", "subprocess.", "ctypes.")) or event in {
        "os.system", "os.posix_spawn", "os.spawn", "os.exec", "os.fork", "os.forkpty",
    }:
        raise PermissionError("Offline policy: network access and external programs are disabled.")


def enable_offline_policy():
    """Install a permanent audit hook before loading UI or business modules."""
    global _enabled
    if not _enabled:
        sys.addaudithook(_deny_external_activity)
        _enabled = True
