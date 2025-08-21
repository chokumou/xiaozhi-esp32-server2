import asyncio
from aiohttp import web, WSMsgType
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler
from core.connection import ConnectionHandler
from core.utils.modules_initialize import initialize_modules
from config.runtime_flags import flags
import os

TAG = __name__


class SimpleHttpServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.ota_handler = OTAHandler(config)
        self.vision_handler = VisionHandler(config)
        # Lazy-initialized modules for WS connections (shared where safe)
        self._vad = None
        self._asr = None
        self._llm = None
        self._memory = None
        self._intent = None

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket")

        if websocket_config and "你" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def start(self):
        server_config = self.config["server"]
        host = server_config.get("ip", "0.0.0.0")
        port = int(server_config.get("http_port", 8003))

        self.logger.bind(tag=TAG).info(f"=== HTTPサーバー起動開始 ===")
        self.logger.bind(tag=TAG).info(f"ホスト: {host}")
        self.logger.bind(tag=TAG).info(f"ポート: {port}")

        if port:
            app = web.Application()

            read_config_from_api = server_config.get("read_config_from_api", False)

            if not read_config_from_api:
                # 如果没有开启智控台，只是单模块运行，就需要再添加简单OTA接口，用于下发websocket接口
                self.logger.bind(tag=TAG).info("OTAルートを追加: /xiaozhi/ota/")
                app.add_routes(
                    [
                        web.get("/xiaozhi/ota/", self.ota_handler.handle_get),
                        web.post("/xiaozhi/ota/", self.ota_handler.handle_post),
                        web.options("/xiaozhi/ota/", self.ota_handler.handle_post),
                        # 同一ハンドラでスラ無しにも対応
                        web.get("/xiaozhi/ota", self.ota_handler.handle_get),
                        web.post("/xiaozhi/ota", self.ota_handler.handle_post),
                        web.options("/xiaozhi/ota", self.ota_handler.handle_post),
                    ]
                )
            # 添加路由
            self.logger.bind(tag=TAG).info("ビジョンルートを追加: /mcp/vision/explain")
            app.add_routes(
                [
                    web.get("/mcp/vision/explain", self.vision_handler.handle_get),
                    web.post("/mcp/vision/explain", self.vision_handler.handle_post),
                    web.options("/mcp/vision/explain", self.vision_handler.handle_post),
                ]
            )

            # ランタイムデバッグ用トグル（再デプロイ不要）
            async def toggle_vad_force(request: web.Request):
                on = request.query.get("on", "")
                if on in ("1", "true", "True"):
                    flags.set("VAD_FORCE_VOICE", True)
                elif on in ("0", "false", "False"):
                    flags.set("VAD_FORCE_VOICE", False)
                return web.json_response({
                    "VAD_FORCE_VOICE": flags.get("VAD_FORCE_VOICE", False),
                    "flags": flags.dump(),
                })
            app.add_routes([web.get("/debug/vad_force_voice", toggle_vad_force)])

            # 合成テスト波形を流し込んでASRパイプラインを検証する簡易エンドポイント
            async def test_audio(request: web.Request):
                # 300msの擬似音声フレーム（20フレーム想定）を送って、強制stop→ASR
                # サイズは小さめのダミーOPUSデータ（decoder側でスキップされてもASR_FORCEを確認する用途）
                try:
                    from core.connection import ConnectionHandler
                    # ダミーWSアダプタを生成して短時間だけ処理
                    class DummyWS:
                        def __init__(self):
                            self.request = type("Req", (), {"headers": {}, "path_qs": "/"})()
                            self.remote_address = ("127.0.0.1", 0)
                            self.closed = False
                            self.state = type("S", (), {"name": "OPEN"})()
                        async def send(self, data):
                            return None
                        async def close(self):
                            self.closed = True
                        def __aiter__(self):
                            return self
                        async def __anext__(self):
                            raise StopAsyncIteration

                    handler = ConnectionHandler(self.config, self._vad, self._asr, self._llm, self._memory, self._intent)
                    # VADバイパスをONにして、ASR→LLM→TTSまで通るか即時検証
                    flags.set("VAD_FORCE_VOICE", True)
                    await handler.handle_connection(DummyWS())
                    return web.json_response({"ok": True, "note": "pipeline primed; speak via normal WS"})
                except Exception as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=500)
            app.add_routes([web.post("/debug/test_audio", test_audio)])

            # 合成サイン波でASRまで通す自己診断（WS不要）
            async def feed_sine(request: web.Request):
                try:
                    import math
                    import numpy as np
                    duration_s = float(request.query.get("duration", "1.0"))
                    freq = float(request.query.get("freq", "440"))
                    frames = int(duration_s * 50)  # およそ20ms単位

                    class DummyWS:
                        def __init__(self):
                            self.request = type("Req", (), {"headers": {}, "path_qs": "/"})()
                            self.remote_address = ("127.0.0.1", 0)
                            self.closed = False
                            self.state = type("S", (), {"name": "OPEN"})()
                            self.sent = []
                        async def send(self, data):
                            self.sent.append(data)
                        async def close(self):
                            self.closed = True
                        def __aiter__(self):
                            return self
                        async def __anext__(self):
                            raise StopAsyncIteration

                    handler = ConnectionHandler(self.config, self._vad, self._asr, self._llm, self._memory, self._intent)
                    handler.websocket = DummyWS()
                    handler.client_listen_mode = "auto"
                    handler.client_have_voice = True
                    handler.client_voice_stop = False
                    handler.audio_format = "pcm"  # PCM直通

                    # VADバイパスで強制的にASRへ
                    flags.set("VAD_FORCE_VOICE", True)

                    # 16kHz, int16 のサイン波をフレーム化
                    sr = 16000
                    t = np.arange(0, int(duration_s * sr))
                    wave = (0.2 * 32767 * np.sin(2 * math.pi * freq * t / sr)).astype(np.int16)
                    frame_len = 320  # 約20ms
                    for i in range(0, len(wave), frame_len):
                        chunk = wave[i:i+frame_len].tobytes()
                        await handleAudioMessage(handler, chunk)

                    # 音声停止シグナル
                    handler.client_voice_stop = True
                    await handleAudioMessage(handler, b"")

                    return web.json_response({
                        "ok": True,
                        "frames": frames,
                        "note": "sine fed; check ASR logs and TTS messages",
                        "sent_messages": getattr(handler.websocket, "sent", [])[-3:],
                    })
                except Exception as e:
                    return web.json_response({"ok": False, "error": str(e)}, status=500)

            app.add_routes([web.get("/debug/feed_sine", feed_sine)])

            # WebSocket route (same port): /xiaozhi/v1/
            self.logger.bind(tag=TAG).info("WebSocketルートを追加: /xiaozhi/v1/")

            async def ws_handler(request: web.Request):
                # Agree on subprotocols; send periodic ping to keep Railway edge alive
                ws = web.WebSocketResponse(protocols=["v1", "xiaozhi-v1"], heartbeat=5)
                await ws.prepare(request)

                # Initialize modules lazily (avoid heavy startup)
                if self._vad is None or self._asr is None or self._llm is None:
                    on_railway = bool(os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT"))
                    modules = initialize_modules(
                        self.logger,
                        self.config,
                        init_vad=not on_railway,
                        init_asr=not on_railway,
                        init_llm=True,
                        init_tts=False,
                        init_memory=True,
                        init_intent=True,
                    )
                    self._vad = modules.get("vad") if self._vad is None else self._vad
                    self._asr = modules.get("asr") if self._asr is None else self._asr
                    self._llm = modules.get("llm") if self._llm is None else self._llm
                    self._memory = modules.get("memory") if self._memory is None else self._memory
                    self._intent = modules.get("intent") if self._intent is None else self._intent

                # Adapter for aiohttp <-> ConnectionHandler expected API
                class _State:
                    @property
                    def name(self):
                        return "CLOSED" if ws.closed else "OPEN"

                class AiohttpWebSocketAdapter:
                    def __init__(self, request: web.Request, ws: web.WebSocketResponse):
                        self._request = request
                        self._ws = ws
                        self.state = _State()

                    @property
                    def request(self):
                        class Req:
                            def __init__(self, r: web.Request):
                                self.headers = r.headers
                                # include query string
                                self.path = r.path_qs
                        return Req(self._request)

                    @property
                    def remote_address(self):
                        return (self._request.remote or "0.0.0.0", 0)

                    @property
                    def closed(self):
                        return self._ws.closed

                    async def send(self, data):
                        if isinstance(data, (bytes, bytearray)):
                            await self._ws.send_bytes(data)
                        else:
                            await self._ws.send_str(str(data))

                    async def close(self):
                        await self._ws.close()

                    def __aiter__(self):
                        return self

                    async def __anext__(self):
                        msg = await self._ws.receive()
                        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                            raise StopAsyncIteration
                        if msg.type == WSMsgType.BINARY:
                            return bytes(msg.data)
                        if msg.type == WSMsgType.TEXT:
                            return msg.data
                        # ignore other types
                        return ""

                adapter = AiohttpWebSocketAdapter(request, ws)
                handler = ConnectionHandler(
                    self.config,
                    self._vad,
                    self._asr,
                    self._llm,
                    self._memory,
                    self._intent,
                )
                await handler.handle_connection(adapter)
                return ws

            app.add_routes([web.get("/xiaozhi/v1/", ws_handler)])

            # 运行服务
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()

            self.logger.bind(tag=TAG).info(f"=== HTTPサーバー起動完了: {host}:{port} ===")

            # 保持服务运行
            while True:
                await asyncio.sleep(3600)  # 每隔 1 小时检查一次
