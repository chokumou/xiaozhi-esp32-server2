@echo off
echo ローカルテスト用xiaozhi-esp32-server2を起動します...

cd main\xiaozhi-server

echo 環境変数を設定しています...
set CHATGLM_API_KEY=0aff2f3341344d9ea724154297e3ef09.Q1LUk2HRWZKlBjF5

echo 設定ファイルをコピーしています...
copy config_railway.yaml config.yaml

echo サーバーを起動しています...
python app.py

pause
