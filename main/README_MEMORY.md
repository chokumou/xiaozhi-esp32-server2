Memory & QUICK_SAVE — 実装メモ
================================

目的
-------
- デバイス発話中にユーザーの重要情報を短期記憶として保存し、後の会話で参照できるようにする。

主な挙動
-------
- トリガー語（`core/data/memory_triggers.txt`）がASR結果に含まれると、`core/providers/asr/base.py` 内で `conn.memory.query_memory(...)` を呼び出す。  
- 保存フローは2段階:  
  1. QUICK_SAVE (即時単一エントリ): 環境変数 `QUICK_SAVE=1` の場合、ASR処理直後に manager API (`/agent/saveMemory/{mac}`) へ非同期PUTを送る。  
  2. Memory provider: `conn.memory.save_memory(...)` を非同期スレッドで実行して、短期記憶要約を作成・ローカルファイル (`data/.memory.yaml`) か manager へ保存する。

JWT / 認証
-------
- manager への呼び出しは通常 server-level secret を使う（`MANAGER_API_SECRET`）。  
- 端末が `Authorization: Bearer <JWT>` を送っている場合、ASR quick-save は接続ヘッダからトークンを取り出し `save_mem_local_short_with_token(..., token=jwt)` を使ってトークンを転送することでユーザー単位の認可を行える。

起動時の設定 (entrypoint)
-------
- Docker イメージの build 時に空の `data/.config.yaml` を書き込む問題を解消するため、起動時に環境変数から `data/.config.yaml` を生成する `entrypoint.sh` を追加した。  
- 参照する環境変数:  
  - `MANAGER_API_URL`  → manager-api の URL  
  - `MANAGER_API_SECRET` → manager-api の server secret（または `JWT_SECRET` の環境名を利用する運用もあり）  
  - `MEMORY_MODULE` → `mem_local_short` など  
  - `QUICK_SAVE` → `1` 有効、`0` 無効（デフォルト0）

動作確認手順
-------
1. Railway の `xiaozhi-esp32-server2` の Variables に `MANAGER_API_URL`, `MANAGER_API_SECRET`, `QUICK_SAVE=1` を設定して redeploy。  
2. 実機で発話: 「記憶して、私の好きな色は青です」 → 続けて「覚えてる？私の好きな色は何？」  
3. サーバログに `[MEM_SAVE] quick save: ok` または `Save memory successful` が出ることを確認。  
4. manager-web の該当エージェントの `summaryMemory` を確認。

トラブルシューティング
-------
- エラー例: `存储短期记忆到服务器失败: 'NoneType' object has no attribute '_execute_request'`  
  - 原因: ManageApiClient が未初期化（config が空で client が作られていない）。  
  - 対処: entrypoint による config 生成を有効化して環境変数を正しく読み込ませる（今回実装済み）。  

今後の改善案
-------
- QUICK_SAVE のレート制御と監視メトリクス導入（高負荷下での保護）。  
- manager 側での冪等処理とトランザクション追跡（重複保存や失敗時のリトライを検討）。  

ファイル
-------
- `core/providers/asr/base.py` — トリガー検出／quick-save 呼び出し箇所  
- `core/providers/memory/mem_local_short/mem_local_short.py` — メモリ保存ロジック（ローカル/manager）  
- `config/manage_api_client.py` — manager への HTTP クライアント + `save_mem_local_short_with_token` 追加  
- `main/README_MEMORY.md` — （このドキュメント）


