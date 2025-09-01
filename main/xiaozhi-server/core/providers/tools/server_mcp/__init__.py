"""服务端MCP工具模块

This module provides lazy/fallback exports so the main server can start even when
the optional `mcp` package is not installed in the environment. If MCP is not
available the exported names are stub classes that raise ImportError when used.
"""

try:
    from .mcp_manager import ServerMCPManager
    from .mcp_executor import ServerMCPExecutor
    from .mcp_client import ServerMCPClient

    __all__ = ["ServerMCPManager", "ServerMCPExecutor", "ServerMCPClient"]
except Exception as _err:  # pragma: no cover - fallback for missing optional deps
    # Define lightweight stubs that raise when instantiated to avoid import-time errors
    class ServerMCPManager:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "optional package 'mcp' is not installed; ServerMCPManager unavailable"
            )

    class ServerMCPExecutor:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "optional package 'mcp' is not installed; ServerMCPExecutor unavailable"
            )

    class ServerMCPClient:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "optional package 'mcp' is not installed; ServerMCPClient unavailable"
            )

    __all__ = ["ServerMCPManager", "ServerMCPExecutor", "ServerMCPClient"]
