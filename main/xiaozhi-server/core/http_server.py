import asyncio
from aiohttp import web
from config.logger import setup_logging
from core.api.ota_handler import OTAHandler
from core.api.vision_handler import VisionHandler

TAG = __name__


class SimpleHttpServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.ota_handler = OTAHandler(config)
        self.vision_handler = VisionHandler(config)

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
            
            # デバッグ用ルート追加
            self.logger.bind(tag=TAG).info("デバッグルートを追加: /debug/routes")
            async def debug_routes(request):
                routes_list = []
                for route in app.router.routes():
                    routes_list.append({
                        "method": route.method,
                        "path": route.resource.canonical,
                        "handler": str(route.handler)
                    })
                return web.json_response(routes_list)
            
            app.add_routes([
                web.get("/debug/routes", debug_routes)
            ])

            # 登録済みルートをログ出力
            self.logger.bind(tag=TAG).info("=== 登録済みルート一覧 ===")
            for route in app.router.routes():
                self.logger.bind(tag=TAG).info(f"ルート: {route.method} {route.resource.canonical}")
            self.logger.bind(tag=TAG).info("=== ルート一覧終了 ===")

            # 运行服务
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()

            self.logger.bind(tag=TAG).info(f"=== HTTPサーバー起動完了: {host}:{port} ===")

            # 保持服务运行
            while True:
                await asyncio.sleep(3600)  # 每隔 1 小时检查一次
