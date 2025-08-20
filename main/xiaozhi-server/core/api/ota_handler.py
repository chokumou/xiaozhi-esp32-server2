import json
import time
from aiohttp import web
import os
from core.utils.util import get_local_ip
from core.api.base_handler import BaseHandler

TAG = __name__


class OTAHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """获取websocket地址

        Args:
            local_ip: 本地IP地址
            port: 端口号

        Returns:
            str: websocket地址
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket", "")

        if websocket_config and "你的" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def handle_post(self, request):
        """处理 OTA POST 请求"""
        try:
            data = await request.text()
            self.logger.bind(tag=TAG).debug(f"OTA请求方法: {request.method}")
            self.logger.bind(tag=TAG).debug(f"OTA请求头: {request.headers}")
            self.logger.bind(tag=TAG).debug(f"OTA请求数据: {data}")

            device_id = request.headers.get("device-id", "")
            if device_id:
                self.logger.bind(tag=TAG).info(f"OTA请求设备ID: {device_id}")
            else:
                raise Exception("OTA请求设备ID为空")

            data_json = json.loads(data)

            server_config = self.config["server"]
            port = int(server_config.get("port", 8000))
            local_ip = get_local_ip()

            # Public base URL for devices (ignore Railway healthcheck host)
            public_base = os.getenv(
                "PUBLIC_BASE_URL",
                "https://xiaozhi-esp32-server2-production.up.railway.app",
            ).rstrip("/")
            ws_url = self._get_websocket_url(local_ip, port)

            return_json = {
                "firmware": {
                    "version": data_json.get("application", {}).get("version", "1.6.8"),
                    "url": "",
                },
                "websocket": {"endpoint": public_base, "port": 443},
                "xiaozhi_websocket": {
                    "ws_url": ws_url,
                    "ws_protocol": "v1",
                    "protocol_version": 1,
                    "origin": public_base,
                },
            }
            response = web.Response(text=json.dumps(return_json, separators=(",", ":")), content_type="application/json")
        except Exception as e:
            return_json = {"success": False, "message": "request error."}
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        finally:
            self._add_cors_headers(response)
            return response

    async def handle_get(self, request):
        """处理 OTA GET 请求"""
        try:
            # デバッグログを追加
            self.logger.bind(tag=TAG).info(f"=== OTA GET リクエスト受信 ===")
            self.logger.bind(tag=TAG).info(f"リクエストURL: {request.url}")
            self.logger.bind(tag=TAG).info(f"リクエストメソッド: {request.method}")
            self.logger.bind(tag=TAG).info(f"リモートIP: {request.remote}")
            self.logger.bind(tag=TAG).info(f"ユーザーエージェント: {request.headers.get('User-Agent', 'N/A')}")
            self.logger.bind(tag=TAG).info(f"全ヘッダー: {dict(request.headers)}")
            
            server_config = self.config["server"]
            local_ip = get_local_ip()
            port = int(server_config.get("port", 8000))

            public_base = os.getenv(
                "PUBLIC_BASE_URL",
                "https://xiaozhi-esp32-server2-production.up.railway.app",
            ).rstrip("/")
            ws_url = self._get_websocket_url(local_ip, port)

            return_json = {
                "firmware": {"version": "1.6.8", "url": ""},
                "websocket": {"endpoint": public_base, "port": 443},
                "xiaozhi_websocket": {
                    "ws_url": ws_url,
                    "ws_protocol": "v1",
                    "protocol_version": 1,
                    "origin": public_base,
                },
            }

            self.logger.bind(tag=TAG).info(f"レスポンス: {return_json}")
            self.logger.bind(tag=TAG).info(f"=== OTA GET リクエスト処理完了 ===")

            response = web.Response(text=json.dumps(return_json, separators=(",", ":")), content_type="application/json")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"OTA GET请求异常: {e}")
            response = web.Response(text="OTA接口异常", content_type="text/plain")
        finally:
            self._add_cors_headers(response)
            return response
