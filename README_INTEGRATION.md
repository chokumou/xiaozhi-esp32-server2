# xiaozhi-esp32-server2 統合アーキテクチャ

## 概要

xiaozhi-esp32-server2は、nekota-serverと連携して完全なAI会話システムを構築します。

## アーキテクチャ

```
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│   ESP32 Device  │    │ xiaozhi-esp32-      │    │   nekota-server │
│                 │◄──►│ server2             │◄──►│                 │
│ - 音声入力      │    │ - AI会話機能        │    │ - メモリ管理    │
│ - 音声出力      │    │ - STT/TTS           │    │ - 認証連携      │
│ - WebSocket     │    │ - LLM処理           │    │ - JWT認証       │
└─────────────────┘    │ - 会話状態管理      │    │ - データベース  │
                       └─────────────────────┘    └─────────────────┘
```

## 機能

### xiaozhi-esp32-server2（メイン機能）
- **音声認識（STT）**: FunASRを使用した高精度音声認識
- **音声合成（TTS）**: EdgeTTSを使用した自然な音声合成
- **大言語モデル（LLM）**: DeepSeek/Qwenを使用したAI会話
- **WebSocket通信**: ESP32とのリアルタイム通信
- **会話状態管理**: listening/speaking状態の制御
- **音声処理**: Opusデコード/エンコード

### nekota-server連携機能
- **認証連携**: JWTトークンの検証と共有
- **メモリ管理**: 会話履歴の保存と取得
- **ユーザー管理**: プロフィール情報の管理
- **データベース**: Supabaseを使用した永続化

## セットアップ

### 1. 環境変数設定

```bash
# xiaozhi-esp32-server2
NEKOTA_SERVER_URL=https://nekota-server-production.up.railway.app
NEKOTA_JWT_SECRET=${JWT_SECRET_KEY}
NEKOTA_API_KEY=${API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}
RAILWAY_STATIC_URL=${RAILWAY_STATIC_URL}
```

### 2. Railwayデプロイ

```bash
# xiaozhi-esp32-server2をRailwayにデプロイ
railway login
railway link
railway up
```

### 3. ESP32設定

```bash
# ESP32ファームウェアのビルドとフラッシュ
idf.py build
idf.py flash
```

## API仕様

### 認証API

```python
# JWTトークン検証
POST /api/auth/verify
{
    "token": "jwt_token_string"
}
```

### メモリ管理API

```python
# メモリ保存
POST /api/memory/save
{
    "user_id": "string",
    "conversation_id": "string",
    "message": "string",
    "response": "string",
    "timestamp": "datetime"
}

# メモリ取得
GET /api/memory/get/{user_id}
```

### 会話履歴API

```python
# 会話履歴保存
POST /api/conversation/save
{
    "user_id": "string",
    "conversation_id": "string",
    "messages": [
        {"role": "user", "content": "string"},
        {"role": "assistant", "content": "string"}
    ],
    "summary": "string"
}
```

## 使用方法

### 1. 基本的な会話

```python
# WebSocket接続
websocket.connect("wss://xiaozhi-esp32-server2-production.up.railway.app/xiaozhi/v1/")

# 音声データ送信
websocket.send(audio_data)

# 応答受信
response = websocket.recv()
```

### 2. メモリ機能の使用

```python
# メモリ保存
await save_memory(user_id, conversation_id, message, response)

# メモリ取得
memories = await get_memories(user_id)
```

## 開発

### ローカル開発

```bash
# 依存関係インストール
pip install -r requirements.txt

# サーバー起動
python app.py
```

### テスト

```bash
# 単体テスト
python -m pytest tests/

# 統合テスト
python -m pytest tests/integration/
```

## トラブルシューティング

### よくある問題

1. **音声認識エラー**
   - FunASRモデルのダウンロード確認
   - 音声フォーマットの確認

2. **WebSocket接続エラー**
   - Railway URLの確認
   - ネットワーク接続の確認

3. **メモリ保存エラー**
   - nekota-serverとの接続確認
   - JWTトークンの有効性確認

## 貢献

1. Fork する
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. Pull Request を作成

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

## サポート

- ドキュメント: [INTEGRATION_SPEC.md](INTEGRATION_SPEC.md)
- 問題報告: [GitHub Issues](https://github.com/chokumou/xiaozhi-esp32-server2/issues)
- ディスカッション: [GitHub Discussions](https://github.com/chokumou/xiaozhi-esp32-server2/discussions)
