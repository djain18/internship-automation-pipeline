"""Safe local TLS setup for networks whose CA is installed in Windows."""

from __future__ import annotations

import os


def enable_system_ca() -> bool:
    """Use the OS trust store on Windows while preserving TLS verification.

    College and corporate networks commonly install a local root certificate in
    the Windows certificate store. Python's bundled CA file cannot see it. The
    optional truststore package bridges that gap without disabling hostname or
    certificate validation. Modal/Linux keeps its normal CA behavior.
    """

    if os.name != "nt":
        return False
    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except ImportError:
        return False

