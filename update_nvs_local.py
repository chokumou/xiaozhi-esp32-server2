#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import serial
import time
import json

def update_nvs_settings():
    """ESP32のNVS設定をローカルサーバー用に更新"""
    
    # シリアルポート設定（必要に応じて変更）
    port = 'COM16'  # ESP32が接続されているポート
    baudrate = 115200
    
    try:
        # シリアル接続
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"シリアルポート {port} に接続しました")
        
        # 少し待機
        time.sleep(2)
        
        # 設定データ
        settings = {
            "new_ota_url": "http://192.168.2.100:8003/xiaozhi/ota/",
            "new_websocket_url": "ws://192.168.2.100:8000/xiaozhi/v1/"
        }
        
        # 設定をJSON形式で送信
        command = f"SET_NVS:{json.dumps(settings)}\n"
        ser.write(command.encode())
        
        print("設定を送信しました:")
        print(f"OTA URL: {settings['new_ota_url']}")
        print(f"WebSocket URL: {settings['new_websocket_url']}")
        
        # 応答を待機
        time.sleep(1)
        
        # 応答を読み取り
        while ser.in_waiting:
            response = ser.readline().decode().strip()
            print(f"ESP32応答: {response}")
        
        ser.close()
        print("設定更新完了！")
        
    except serial.SerialException as e:
        print(f"シリアルポートエラー: {e}")
        print("ESP32が正しいポートに接続されているか確認してください")
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    print("ESP32のNVS設定をローカルサーバー用に更新します")
    print("ESP32がシリアルポートに接続されていることを確認してください")
    
    # ポート番号を確認
    port = input("ESP32のシリアルポートを入力してください（例: COM3）: ").strip()
    
    if port:
        # ポート番号を更新
        import re
        with open(__file__, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(r"port = 'COM\d+'", f"port = '{port}'", content)
        with open(__file__, 'w', encoding='utf-8') as f:
            f.write(content)
    
    update_nvs_settings()
