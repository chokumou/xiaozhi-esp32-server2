import asyncio
import websockets
import json
from config.logger import setup_logging
from core.connection import ConnectionHandler
from config.config_loader import get_config_from_api
from core.utils.modules_initialize import initialize_modules
from core.utils.util import check_vad_update, check_asr_update
import os

TAG = __name__


class WebSocketServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.config_lock = asyncio.Lock()
        # Railwayでは起動を速くするためASRは遅延初期化
        on_railway = bool(os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT"))
        init_asr_now = not on_railway
        init_vad_now = not on_railway
        modules = initialize_modules(
            self.logger,
            self.config,
            ("VAD" in self.config["selected_module"]) and init_vad_now,
            init_asr_now,
            "LLM" in self.config["selected_module"],
            False,
            "Memory" in self.config["selected_module"],
            "Intent" in self.config["selected_module"],
        )
        self._vad = modules["vad"] if "vad" in modules else None
        self._asr = modules["asr"] if "asr" in modules else None
        self._llm = modules["llm"] if "llm" in modules else None
        self._intent = modules["intent"] if "intent" in modules else None
        self._memory = modules["memory"] if "memory" in modules else None

        self.active_connections = set()

    def _ensure_asr_initialized(self):
        if self._asr is None:
            modules = initialize_modules(
                self.logger,
                self.config,
                False,
                True,
                False,
                False,
                False,
                False,
            )
            if "asr" in modules:
                self._asr = modules["asr"]

    def _ensure_vad_initialized(self):
        if self._vad is None:
            modules = initialize_modules(
                self.logger,
                self.config,
                True,
                False,
                False,
                False,
                False,
                False,
            )
            if "vad" in modules:
                self._vad = modules["vad"]

    async def start(self):
        server_config = self.config["server"]
        host = server_config.get("ip", "0.0.0.0")
        port = int(server_config.get("port", 8000))

        async with websockets.serve(
            self._handle_connection, host, port, process_request=self._http_response
        ):
            await asyncio.Future()

    async def _handle_connection(self, websocket):
        """处理新连接，每次创建独立的ConnectionHandler"""
        # 创建ConnectionHandler时传入当前server实例
        handler = ConnectionHandler(
            self.config,
            (self._vad or (self._ensure_vad_initialized() or self._vad)),
            (self._asr or (self._ensure_asr_initialized() or self._asr)),
            self._llm,
            self._memory,
            self._intent,
            self,  # 传入server实例
        )
        self.active_connections.add(handler)
        try:
            await handler.handle_connection(websocket)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"处理连接时出错: {e}")
        finally:
            # 确保从活动连接集合中移除
            self.active_connections.discard(handler)
            # 强制关闭连接（如果还没有关闭的话）
            try:
                # 安全地检查WebSocket状态并关闭
                if hasattr(websocket, "closed") and not websocket.closed:
                    await websocket.close()
                elif hasattr(websocket, "state") and websocket.state.name != "CLOSED":
                    await websocket.close()
                else:
                    # 如果没有closed属性，直接尝试关闭
                    await websocket.close()
            except Exception as close_error:
                self.logger.bind(tag=TAG).error(
                    f"服务器端强制关闭连接时出错: {close_error}"
                )

    async def _http_response(self, *args, **kwargs):
        # Support websockets process_request signatures across versions:
        # - (path, request_headers)
        # - (websocket, request_headers) with websocket.respond(...)
        if len(args) >= 2 and isinstance(args[0], str):
            path = args[0]
            request_headers = args[1]
            use_tuple = True
        else:
            websocket = args[0]
            request_headers = args[1]
            # derive path if available
            path = kwargs.get("path", "/")
            use_tuple = False
        # 非WSのHTTPヘルスチェック/OTA応答をここで返す
        # WebSocketハンドシェイク以外のリクエストはここに来る
        try:
            connection_hdr = request_headers.get("Connection", "").lower()
            upgrade_hdr = request_headers.get("Upgrade", "").lower()
            if "upgrade" in connection_hdr or upgrade_hdr == "websocket":
                return None  # WSはそのまま続行

            host = request_headers.get("Host", "localhost")
            scheme = "https"  # RailwayはTLS終端

            # どのパスでもヘルス用JSONを返す（Railway/プリフライト用）
            return_json = {
                "firmware": {"version": "1.6.8", "url": ""},
                "websocket": {"endpoint": f"{scheme}://{host}", "port": 443},
                "xiaozhi_websocket": {
                    "ws_url": f"wss://{host}/xiaozhi/v1/",
                    "ws_protocol": "xiaozhi-v1",
                    "protocol_version": 1,
                    "origin": f"{scheme}://{host}",
                },
            }
            body = json.dumps(return_json, separators=(",", ":")).encode("utf-8")
            headers = [
                ("Content-Type", "application/json"),
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Headers", "*"),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
            ]
            if use_tuple:
                return 200, headers, body
            else:
                return await websocket.respond(200, body=body, headers=headers)
        except Exception:
            body = b"Internal Server Error\n"
            headers = [("Content-Type", "text/plain; charset=utf-8")]
            if use_tuple:
                return 500, headers, body
            else:
                return await websocket.respond(500, body=body, headers=headers)

    async def update_config(self) -> bool:
        """更新服务器配置并重新初始化组件

        Returns:
            bool: 更新是否成功
        """
        try:
            async with self.config_lock:
                # 重新获取配置
                new_config = get_config_from_api(self.config)
                if new_config is None:
                    self.logger.bind(tag=TAG).error("获取新配置失败")
                    return False
                self.logger.bind(tag=TAG).info(f"获取新配置成功")
                # 检查 VAD 和 ASR 类型是否需要更新
                update_vad = check_vad_update(self.config, new_config)
                update_asr = check_asr_update(self.config, new_config)
                self.logger.bind(tag=TAG).info(
                    f"检查VAD和ASR类型是否需要更新: {update_vad} {update_asr}"
                )
                # 更新配置
                self.config = new_config
                # 重新初始化组件
                modules = initialize_modules(
                    self.logger,
                    new_config,
                    update_vad,
                    update_asr,
                    "LLM" in new_config["selected_module"],
                    False,
                    "Memory" in new_config["selected_module"],
                    "Intent" in new_config["selected_module"],
                )

                # 更新组件实例
                if "vad" in modules:
                    self._vad = modules["vad"]
                if "asr" in modules:
                    self._asr = modules["asr"]
                if "llm" in modules:
                    self._llm = modules["llm"]
                if "intent" in modules:
                    self._intent = modules["intent"]
                if "memory" in modules:
                    self._memory = modules["memory"]
                self.logger.bind(tag=TAG).info(f"更新配置任务执行完毕")
                return True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"更新服务器配置失败: {str(e)}")
            return False
