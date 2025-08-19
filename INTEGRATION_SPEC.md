# xiaozhi-esp32-server2 と nekota-server 統合仕様書

## 概要

xiaozhi-esp32-server2をメインのAI会話機能として使用し、nekota-serverはメモリ管理と認証連携を担当する統合アーキテクチャ。

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

## 機能分担

### xiaozhi-esp32-server2（メイン機能）
- **音声認識（STT）**: FunASRを使用
- **音声合成（TTS）**: EdgeTTSを使用
- **大言語モデル（LLM）**: DeepSeek/Qwenを使用
- **WebSocket通信**: ESP32とのリアルタイム通信
- **会話状態管理**: listening/speaking状態制御
- **音声処理**: Opusデコード/エンコード

### nekota-server（連携機能）
- **認証連携**: JWTトークンの検証と共有
- **メモリ管理**: 会話履歴の保存と取得
- **ユーザー管理**: プロフィール情報の管理
- **データベース**: Supabaseを使用した永続化

## API設計

### 1. 認証連携

#### JWT共有方式
```python
# xiaozhi-esp32-server2側
import jwt
from nekota_server_auth import verify_jwt_token

async def verify_user_token(token: str):
    """nekota-serverのJWTトークンを検証"""
    try:
        # nekota-serverのJWT_SECRET_KEYを使用
        payload = jwt.decode(token, nekota_jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.InvalidTokenError:
        return None
```

#### 認証エンドポイント
```python
# nekota-server側
@app.post("/api/auth/verify")
async def verify_token(token: str):
    """xiaozhi-esp32-server2からのトークン検証要求"""
    return {"valid": True, "user_id": user_id}
```

### 2. メモリ管理

#### メモリ保存API
```python
# xiaozhi-esp32-server2 → nekota-server
POST /api/memory/save
{
    "user_id": "string",
    "conversation_id": "string",
    "message": "string",
    "response": "string",
    "timestamp": "datetime"
}
```

#### メモリ取得API
```python
# xiaozhi-esp32-server2 ← nekota-server
GET /api/memory/get/{user_id}
Response: {
    "memories": [
        {
            "conversation_id": "string",
            "summary": "string",
            "last_updated": "datetime"
        }
    ]
}
```

### 3. 会話履歴管理

#### 履歴保存
```python
# 会話終了時にnekota-serverに送信
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

## 実装手順

### Phase 1: 基本連携
1. **JWT認証連携**: 両サーバー間でJWTトークンを共有
2. **メモリAPI実装**: nekota-serverにメモリ保存/取得APIを追加
3. **xiaozhi-esp32-server2修正**: nekota-serverとの通信機能を追加

### Phase 2: 高度な機能
1. **会話履歴**: 長期記憶機能の実装
2. **ユーザー設定**: 個人設定の同期
3. **統計情報**: 使用状況の記録

### Phase 3: 最適化
1. **キャッシュ**: 頻繁にアクセスするデータのキャッシュ
2. **エラーハンドリング**: 接続エラー時のフォールバック
3. **パフォーマンス**: レスポンス時間の最適化

## 環境変数設定

### xiaozhi-esp32-server2
```bash
# nekota-server連携設定
NEKOTA_SERVER_URL=https://nekota-server-production.up.railway.app
NEKOTA_JWT_SECRET=${JWT_SECRET_KEY}
NEKOTA_API_KEY=${API_KEY}

# 既存設定
OPENAI_API_KEY=${OPENAI_API_KEY}
RAILWAY_STATIC_URL=${RAILWAY_STATIC_URL}
```

### nekota-server
```bash
# 既存設定（変更なし）
JWT_SECRET_KEY=${JWT_SECRET_KEY}
SUPABASE_URL=${SUPABASE_URL}
SUPABASE_KEY=${SUPABASE_KEY}
```

## デプロイ構成

### Railway設定
1. **xiaozhi-esp32-server2**: メインのAI会話サービス
2. **nekota-server**: メモリ管理と認証サービス
3. **ESP32**: 両サーバーと通信

### 通信フロー
```
ESP32 → xiaozhi-esp32-server2 (音声処理)
xiaozhi-esp32-server2 → nekota-server (メモリ保存/取得)
nekota-server → xiaozhi-esp32-server2 (認証確認)
xiaozhi-esp32-server2 → ESP32 (音声応答)
```

## セキュリティ考慮事項

1. **JWT共有**: 両サーバーで同じJWT_SECRET_KEYを使用
2. **API認証**: nekota-server間の通信にAPIキーを使用
3. **HTTPS通信**: 全ての通信をHTTPSで暗号化
4. **レート制限**: API呼び出し回数の制限

## テスト計画

1. **単体テスト**: 各APIエンドポイントのテスト
2. **統合テスト**: 両サーバー間の通信テスト
3. **エンドツーエンドテスト**: ESP32からの完全な会話フロー
4. **負荷テスト**: 同時接続数のテスト

## 今後の拡張

1. **マルチユーザー**: 複数ユーザーの同時利用
2. **音声認識精度向上**: より高精度なSTT
3. **感情認識**: 音声から感情を読み取る機能
4. **多言語対応**: より多くの言語に対応
