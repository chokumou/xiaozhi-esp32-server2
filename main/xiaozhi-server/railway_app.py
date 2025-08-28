from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import time
import os

app = FastAPI()

@app.get("/")
async def root():
    return {"Hello": "World"}

@app.get("/xiaozhi/ota/")
async def ota_get():
    """OTA GET エンドポイント"""
    try:
        # nekota-serverの形式に合わせてレスポンスを修正
        return_json = {
            "firmware": {
                "version": "1.6.8",
                "url": "",
            },
            "websocket": {
                "endpoint": "https://xiaozhi-esp32-server2-production.up.railway.app",
                "port": 443
            },
            "xiaozhi_websocket": {
                "ws_url": "wss://xiaozhi-esp32-server2-production.up.railway.app/xiaozhi/v1/",
                "ws_protocol": "xiaozhi-v1",
                "protocol_version": 1,
                "origin": "https://xiaozhi-esp32-server2-production.up.railway.app"
            }
        }
        
        print(f"OTA GET レスポンス: {return_json}")
        return return_json
        
    except Exception as e:
        print(f"OTA GET エラー: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@app.post("/xiaozhi/ota/")
async def ota_post(request: Request):
    """OTA POST エンドポイント"""
    try:
        # リクエストデータを取得
        data = await request.json()
        print(f"OTA POST リクエスト: {data}")
        
        # nekota-serverの形式に合わせてレスポンスを修正
        return_json = {
            "firmware": {
                "version": data.get("application", {}).get("version", "1.6.8"),
                "url": "",
            },
            "websocket": {
                "endpoint": "https://xiaozhi-esp32-server2-production.up.railway.app",
                "port": 443
            },
            "xiaozhi_websocket": {
                "ws_url": "wss://xiaozhi-esp32-server2-production.up.railway.app/xiaozhi/v1/",
                "ws_protocol": "xiaozhi-v1",
                "protocol_version": 1,
                "origin": "https://xiaozhi-esp32-server2-production.up.railway.app"
            }
        }
        
        print(f"OTA POST レスポンス: {return_json}")
        return return_json
        
    except Exception as e:
        print(f"OTA POST エラー: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@app.get("/debug/routes")
async def debug_routes():
    """デバッグ用：登録済みルート一覧"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "methods": route.methods,
            "name": route.name
        })
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


