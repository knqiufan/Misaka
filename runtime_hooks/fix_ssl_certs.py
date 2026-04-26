"""
PyInstaller runtime hook - fix SSL certificate verification on Windows.

When packaged with PyInstaller, the bundled Python may not find the system
CA certificate store, causing SSL verification failures when any library
(e.g. flet_desktop, urllib, httpx) attempts HTTPS requests.

This hook sets SSL_CERT_FILE to the certifi CA bundle if present,
falling back to the Windows system certificate store path.
"""

import os
import sys


def _fix_ssl_certs() -> None:
    if os.environ.get("SSL_CERT_FILE"):
        return

    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        return
    except ImportError:
        pass

    if sys.platform == "win32":
        import ssl
        ctx = ssl.create_default_context()
        ctx.load_default_certs()


if getattr(sys, "frozen", False):
    _fix_ssl_certs()
