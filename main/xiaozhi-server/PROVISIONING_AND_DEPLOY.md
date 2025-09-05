短いメモ: プロビジョニングとローカル検証手順

- 目的: 電子端末（ESP32）から送信される JWT を受け取り、nekota-server のローカルメモ保存（mem_local_short）をテストするための最低限手順。

準備:
- `main/xiaozhi-server` を起動できる Python 環境を用意。
- `data/.config.yaml` に `selected_module.Memory: mem_local_short` と `QUICK_SAVE: "1"` を設定。
- `test/emulate_device_ws.py` を使って WebSocket 接続をエミュレート可能。

手順:
1. サーバ起動: `python app.py`（ログを観察）
2. Device JWT を用意（既存の JWT を使用するか、`core/utils/auth.py` で生成）
3. エミュレータ実行:
   `python test/emulate_device_ws.py --url ws://localhost:8090/ws --device-id test-device --token <JWT>`
4. サーバログで `[MEM_SAVE]` の行が出ることを確認。



