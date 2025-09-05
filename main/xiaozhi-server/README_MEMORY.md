# Memory / Provisioning — 変更まとめと手順

このファイルは今回の「メモリ保存」「プロビジョニング」「Railway デプロイ」周りの変更点と、再現・復旧手順を短くまとめたものです。問題が起きたときにこの手順通りに辿れば復旧できるレベルに書いてあります。

- 変更日: see git history (最新コミット: `29fa675`)

--- 変更の要点 (サーバ側)
- `QUICK_SAVE` サポートを追加: ASR パイプラインから即時（非同期）で短期メモリを manager-api に保存する仕組みを追加。
- JWT フォワーディング: デバイスが送る JWT を使って manager-api を呼べるように `save_mem_local_short_with_token` を追加。
- プロビジョニング API を追加: FastAPI 用の `/provision` と、aiohttp ベースの HTTP サーバ用のフォールバック `/provision` ハンドラを追加。
- Docker / Railway 対応:
  - 軽量ビルド用 `main/xiaozhi-server/requirements.railway.txt` を追加。
  - `xiaozhi-esp32-server2/Dockerfile-railway` を用意し、ビルド時に巨大な ML ライブラリをインストールしないようにした。
  - root の `requirements.txt` の `pydantic` バージョンを緩和（依存衝突対策）。

--- 変更の要点 (デバイス側・備考)
- ファームウェア側で `hello` JSON に `token` フィールドを載せるように修正すると、サーバ側で hello 受信時に `conn.headers['authorization']` に保存して JWT を利用できる。
- 代替として、デバイスは WebSocket の最初の接続ヘッダに `Authorization: Bearer <JWT>` を付与する実装が推奨。

--- 必要な環境変数（Railway に設定）
- `MANAGER_API_URL` — manager API の URL
- `MANAGER_API_SECRET` — manager API の server secret
- `QUICK_SAVE` — 開発用に `1` にすると quick-save を有効化
- `MEMORY_MODULE` — メモリモジュール名（例: `mem_local_short`）
- `PROVISION_ADMIN_KEY` — プロビジョニング用の管理キー
- `JWT_SECRET_KEY` — サーバ内で発行する JWT を署名する鍵（必須）

--- Railway デプロイ手順（短く）
1. `Dockerfile path` を `xiaozhi-esp32-server2/Dockerfile-railway` に設定する（Railway UI の Deploy settings）。
2. `MANAGER_API_*` と `PROVISION_ADMIN_KEY` など上記 env を Railway の Variables に設定する。
3. Git に変更を push → Railway が自動ビルド & デプロイ。

--- 動作確認コマンド
- ルート確認:
  - `curl -i https://<app>/`  (FastAPI root は 404 もあり得る)
- OTA 形式応答:
  - `curl -i https://<app>/xiaozhi/ota/`  (簡易 OTA ルート)
- メモリ・ASR デバッグ:
  - `curl -i https://<app>/debug/feed_sine?duration=0.1`  (サイン波で ASR パイプラインを起動、成功時に `{"ok": true, "frames": ...}` を返す)
- ルート一覧:
  - `curl -i https://<app>/debug/routes`  (登録済みルートの確認)
- プロビジョニング（管理キーを使って JWT 発行）:
  - PowerShell:
    ```powershell
    $admin=(Get-Content 'env_bk' | Select-String '^PROVISION_ADMIN_KEY=').Line.Split('=')[1].Trim()
    Invoke-RestMethod -Method Post -Uri ($server + '/provision') -Headers @{ 'x-admin-key' = $admin; 'Content-Type' = 'application/json' } -Body (@{ device_id = '<DEVICE_ID>' } | ConvertTo-Json)
    ```
  - curl:
    ```bash
    curl -i -X POST -H "x-admin-key: <ADMIN_KEY>" -H "Content-Type: application/json" -d '{"device_id":"<ID>"}' https://<app>/provision
    ```

--- よくある障害と復旧手順（短く）
1) ビルドで `ModuleNotFoundError: No module named 'fastapi'` の場合：
   - root ではなく `Dockerfile-railway` を使うよう設定されているか確認。
   - `requirements.railway.txt` を使っていることを確認。`fastapi` が含まれている。

2) pip の依存衝突 / 解決不能（ResolutionImpossible）:
   - `pydantic` の固定を緩和済み。もし他のパッケージが矛盾する場合は、`requirements.railway.txt` に必要最小限のみを残し、重い ML パッケージは除外する。

3) デプロイは走るが `/provision` が 404 の場合：
   - サーバ種別（FastAPI vs aiohttp）によりエンドポイント登録場所が異なる。今回両方にハンドラを用意した。
   - `curl -i https://<app>/debug/routes` でルート一覧を確認する。

4) Manager API 呼び出し時に `NoneType._execute_request` エラーが出る場合：
   - `data/.config.yaml` に `manager-api.url` と `manager-api.secret` が正しく設定されているかを確認。Railway では `entrypoint.sh` が環境変数から `data/.config.yaml` を生成するようにしている。

--- 重要なファイル（参照）
- `main/xiaozhi-server/core/providers/asr/base.py` — quick-save 呼び出し箇所
- `main/xiaozhi-server/config/manage_api_client.py` — manager API 呼び出し、`save_mem_local_short_with_token` を追加
- `main/xiaozhi-server/entrypoint.sh` — 環境変数から `data/.config.yaml` を生成
- `xiaozhi-esp32-server2/Dockerfile-railway` — Railway 用 Dockerfile
- `main/xiaozhi-server/requirements.railway.txt` — Railway 用最小依存
- `main/xiaozhi-server/core/api/provisioning.py` — FastAPI 用 `/provision`
- `main/xiaozhi-server/core/http_server.py` — aiohttp 用 `/provision` フォールバック

--- 今後やること（TODO）
- デバイス側: NVS に JWT を保存して WebSocket 接続ヘッダに `Authorization` を付けるユーティリティを追加する。
- サーバ側: `ManageApiClient` の JWT 検証を Supabase などに移行する（長期運用用）。
- 運用: 本番では `QUICK_SAVE=0` を推奨（不要な即時保存を避ける）。

--- 連絡先
このドキュメントに不明点があれば、実行したコマンドの出力（railway の deploy logs の ERROR 部分）を貼ってください。修正パッチを作成します。



