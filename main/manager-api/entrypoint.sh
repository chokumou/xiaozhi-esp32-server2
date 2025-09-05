#!/bin/sh
set -e

# プロファイル設定（環境変数で制御）  
# デフォルトはH2（安全のため）
SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-local}"

# 強制的にlocalプロファイルに設定（緊急対処）
SPRING_PROFILES_ACTIVE="local"
export SPRING_PROFILES_ACTIVE

echo "Starting Manager API"
echo "Port: 8002"
echo "Profile: $SPRING_PROFILES_ACTIVE"
echo "Features: Device Management, OTA Management, Token Auth"

# 強制的にPostgreSQL環境変数をクリア（H2使用のため）
echo "Forcing H2 Database (clearing all PostgreSQL env vars)"
unset SPRING_DATASOURCE_URL
unset SPRING_DATASOURCE_USERNAME 
unset SPRING_DATASOURCE_PASSWORD
unset SPRING_DATASOURCE_DRIVER_CLASS_NAME
unset SPRING_DATASOURCE_DRUID_URL
unset SPRING_DATASOURCE_DRUID_USERNAME
unset SPRING_DATASOURCE_DRUID_PASSWORD
unset SPRING_DATASOURCE_DRUID_DRIVER_CLASS_NAME

exec java $JAVA_OPTS -Dspring.profiles.active=$SPRING_PROFILES_ACTIVE -jar /app/app.jar