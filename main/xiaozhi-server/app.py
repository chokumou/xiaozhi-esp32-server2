import sys
import uuid
import signal
import asyncio
from aioconsole import ainput
import os
import yaml
from config.settings import load_config
from config.logger import setup_logging
from core.utils.util import get_local_ip, validate_mcp_endpoint
from core.http_server import SimpleHttpServer
from core.websocket_server import WebSocketServer
from core.utils.util import check_ffmpeg_installed

TAG = __name__
logger = setup_logging()


def ensure_runtime_config():
    """Railway環境で設定ファイルが無い場合、環境変数から生成"""
    import os
    
    # 現在の作業ディレクトリを確認
    current_dir = os.getcwd()
    logger.bind(tag=TAG).info(f"※ここだよ！ 現在の作業ディレクトリ: {current_dir}")
    
    # 複数の候補パスを試す
    candidate_paths = [
        "/opt/xiaozhi-esp32-server/data/.config.yaml",
        f"{current_dir}/data/.config.yaml",
        f"{os.path.dirname(current_dir)}/data/.config.yaml"
    ]
    
    for config_path in candidate_paths:
        logger.bind(tag=TAG).info(f"※ここだよ！ 候補パス確認: {config_path}")
        
        # ディレクトリ作成
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 設定ファイルが存在しない、かつ環境変数が設定されている場合のみ生成
        if not os.path.exists(config_path):
            manager_api_url = os.getenv("MANAGER_API_URL", "")
            manager_api_secret = os.getenv("MANAGER_API_SECRET", "")
            memory_module = os.getenv("MEMORY_MODULE", "nomem")
            quick_save = os.getenv("QUICK_SAVE", "0")
            
            logger.bind(tag=TAG).info(f"※ここだよ！ 環境変数から設定ファイル生成: {config_path}")
            logger.bind(tag=TAG).info(f"※ここだよ！ MANAGER_API_URL: '{manager_api_url}'")
            logger.bind(tag=TAG).info(f"※ここだよ！ MANAGER_API_SECRET: '{manager_api_secret[:10]}...' (length={len(manager_api_secret)})")
            logger.bind(tag=TAG).info(f"※ここだよ！ MEMORY_MODULE: '{memory_module}'")
            logger.bind(tag=TAG).info(f"※ここだよ！ QUICK_SAVE: '{quick_save}'")
            
            if manager_api_url and manager_api_secret:
                config_data = {
                    "manager-api": {
                        "url": manager_api_url,
                        "secret": manager_api_secret
                    },
                    "selected_module": {
                        "Memory": memory_module
                    },
                    "QUICK_SAVE": quick_save
                }
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                    f.flush()  # 強制的にディスクに書き込み
                    os.fsync(f.fileno())  # システムレベルでの同期
                
                # 書き込み確認
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        verify_content = f.read()
                    logger.bind(tag=TAG).info(f"※ここだよ！ 設定ファイル生成完了: {config_path}")
                    logger.bind(tag=TAG).info(f"※ここだよ！ 書き込み確認成功: {len(verify_content)}文字")
                else:
                    logger.bind(tag=TAG).error(f"※ここだよ！ 設定ファイル書き込み失敗: {config_path}")
                
                # キャッシュをクリアして再読み込みを強制
                try:
                    from core.utils.cache.manager import cache_manager, CacheType
                    cache_manager.clear(CacheType.CONFIG, "main_config")
                    logger.bind(tag=TAG).info("※ここだよ！ 設定キャッシュをクリア")
                except Exception as e:
                    logger.bind(tag=TAG).warning(f"※ここだよ！ キャッシュクリア失敗: {e}")
                
                return  # 成功したら終了
            else:
                logger.bind(tag=TAG).warning("※ここだよ！ 環境変数不足のため設定ファイル生成をスキップ")
        else:
            logger.bind(tag=TAG).info(f"※ここだよ！ 設定ファイル既存: {config_path}")
            return  # 既存ファイルがあれば終了


async def wait_for_exit() -> None:
    """
    阻塞直到收到 Ctrl‑C / SIGTERM。
    - Unix: 使用 add_signal_handler
    - Windows: 依赖 KeyboardInterrupt
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if sys.platform != "win32":  # Unix / macOS
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    else:
        # Windows：await一个永远pending的fut，
        # 让 KeyboardInterrupt 冒泡到 asyncio.run，以此消除遗留普通线程导致进程退出阻塞的问题
        try:
            await asyncio.Future()
        except KeyboardInterrupt:  # Ctrl‑C
            pass


async def monitor_stdin():
    """监控标准输入，消费回车键"""
    while True:
        await ainput()  # 异步等待输入，消费回车


async def main():
    check_ffmpeg_installed()
    
    # Railway環境用の設定ファイル生成
    ensure_runtime_config()
    
    config = load_config()
    
    # ManageApiClient初期化
    try:
        from config.manage_api_client import ManageApiClient
        manager_api_config = config.get("manager-api")
        logger.bind(tag=TAG).info(f"※ここだよ！ config全体: {list(config.keys())}")
        logger.bind(tag=TAG).info(f"※ここだよ！ manager-api設定: {manager_api_config}")
        
        if manager_api_config:
            api_client = ManageApiClient(config)
            logger.bind(tag=TAG).info("※ここだよ！ ManageApiClient初期化成功")
        else:
            logger.bind(tag=TAG).warning("※ここだよ！ manager-api設定が見つかりません")
    except Exception as e:
        logger.bind(tag=TAG).error(f"※ここだよ！ ManageApiClient初期化失敗: {e}")
        import traceback
        logger.bind(tag=TAG).error(f"※ここだよ！ ManageApiClient初期化失敗詳細: {traceback.format_exc()}")

    # Railway 環境では単一ポート($PORT)のみ公開されるため、WebSocketサーバーをそのポートで起動し、
    # HTTPヘルスチェック/OTAはwebsocketsのprocess_requestで応答する。
    railway_project_id = os.getenv("RAILWAY_PROJECT_ID")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT")
    on_railway = bool(railway_project_id or railway_env)
    if on_railway:
        port_env = int(os.getenv("PORT", config.get("server", {}).get("port", 8000)))
        config.setdefault("server", {})
        config["server"]["port"] = port_env
        # http_portは使用しない（同一ポート重複バインドを避ける）
        config["server"]["http_port"] = port_env

    # 默认使用manager-api的secret作为auth_key
    # 如果secret为空，则生成随机密钥
    # auth_key用于jwt认证，比如视觉分析接口的jwt认证
    auth_key = config.get("manager-api", {}).get("secret", "")
    if not auth_key or len(auth_key) == 0 or "你" in auth_key:
        auth_key = str(uuid.uuid4().hex)
    config["server"]["auth_key"] = auth_key

    # 添加 stdin 监控任务
    stdin_task = asyncio.create_task(monitor_stdin())

    # RailwayではHTTP+WSを同一ポートのSimpleHttpServerで提供
    ws_task = None
    ota_task = None
    if on_railway:
        server = SimpleHttpServer(config)
        ota_task = asyncio.create_task(server.start())
    else:
        # ローカルは従来どおり別プロセス
        ws_server = WebSocketServer(config)
        ws_task = asyncio.create_task(ws_server.start())
        ota_server = SimpleHttpServer(config)
        ota_task = asyncio.create_task(ota_server.start())

    read_config_from_api = config.get("read_config_from_api", False)
    port = int(config["server"].get("http_port", 8003))
    if not read_config_from_api and not on_railway:
        logger.bind(tag=TAG).info(
            "OTA接口是\t\thttp://{}:{}/xiaozhi/ota/",
            get_local_ip(),
            port,
        )
        logger.bind(tag=TAG).info(
            "视觉分析接口是\thttp://{}:{}/mcp/vision/explain",
            get_local_ip(),
            port,
        )
    mcp_endpoint = config.get("mcp_endpoint", None)
    if mcp_endpoint is not None and "你" not in mcp_endpoint:
        # 校验MCP接入点格式
        if validate_mcp_endpoint(mcp_endpoint):
            logger.bind(tag=TAG).info("mcp接入点是\t{}", mcp_endpoint)
            # 将mcp计入点地址转成调用点
            mcp_endpoint = mcp_endpoint.replace("/mcp/", "/call/")
            config["mcp_endpoint"] = mcp_endpoint
        else:
            logger.bind(tag=TAG).error("mcp接入点不符合规范")
            config["mcp_endpoint"] = "你的接入点 websocket地址"

    # 获取WebSocket配置，使用安全的默认值
    websocket_port = 8000
    server_config = config.get("server", {})
    if isinstance(server_config, dict):
        websocket_port = int(server_config.get("port", 8000))

    logger.bind(tag=TAG).info(
        "Websocket地址是\tws://{}:{}/xiaozhi/v1/",
        get_local_ip(),
        websocket_port,
    )

    logger.bind(tag=TAG).info(
        "=======上面的地址是websocket协议地址，请勿用浏览器访问======="
    )
    logger.bind(tag=TAG).info(
        "如想测试websocket请用谷歌浏览器打开test目录下的test_page.html"
    )
    logger.bind(tag=TAG).info(
        "=============================================================\n"
    )

    try:
        await wait_for_exit()  # 阻塞直到收到退出信号
    except asyncio.CancelledError:
        print("任务被取消，清理资源中...")
    finally:
        # 取消所有任务（关键修复点）
        stdin_task.cancel()
        ws_task.cancel()
        if ota_task:
            ota_task.cancel()

        # 等待任务终止（必须加超时）
        await asyncio.wait(
            [stdin_task, ws_task, ota_task] if ota_task else [stdin_task, ws_task],
            timeout=3.0,
            return_when=asyncio.ALL_COMPLETED,
        )
        print("服务器已关闭，程序退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("手动中断，程序终止。")
