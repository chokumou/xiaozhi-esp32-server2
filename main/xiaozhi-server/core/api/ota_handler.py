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
        """处理 OTA POST 请求（设备からのPOSTは必ず200でJSONを返す）"""
        try:
            # デバイスはJSON以外を送る場合があるため、本文は参照のみ
            _ = await request.read()
            self.logger.bind(tag=TAG).debug(f"OTA POST headers: {dict(request.headers)}")

            server_config = self.config["server"]
            port = int(server_config.get("port", 8000))
            local_ip = get_local_ip()

            public_base = os.getenv(
                "PUBLIC_BASE_URL",
                "https://xiaozhi-esp32-server2-production.up.railway.app",
            )
            # 末尾の空白やセミコロン/スラッシュを除去
            public_base = public_base.strip().rstrip("/;")

            ws_url = self._get_websocket_url(local_ip, port)
            ws_url = ws_url.strip().rstrip(";")

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
            response = web.Response(text=json.dumps(return_json, separators=(",", ":")), content_type="application/json")
        except Exception:
            # 例外時も200で空の構造を返す
            fallback = {
                "firmware": {"version": "1.6.8", "url": ""},
                "websocket": {"endpoint": "", "port": 0},
                "xiaozhi_websocket": {
                    "ws_url": "",
                    "ws_protocol": "v1",
                    "protocol_version": 1,
                    "origin": "",
                },
            }
            response = web.Response(text=json.dumps(fallback, separators=(",", ":")), content_type="application/json")
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
            )
            # 末尾の空白やセミコロン/スラッシュを除去
            public_base = public_base.strip().rstrip("/;")

            ws_url = self._get_websocket_url(local_ip, port)
            ws_url = ws_url.strip().rstrip(";")

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
