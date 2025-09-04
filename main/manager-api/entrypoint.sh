#!/bin/sh
set -e

APP_ENV_FILE=/app/.env
if [ -f "$APP_ENV_FILE" ]; then
  echo "Loading env from $APP_ENV_FILE"
  # export all variables from file
  set -o allexport
  . "$APP_ENV_FILE"
  set +o allexport
else
  echo ".env file not found, using environment variables directly"
fi

echo "Starting manager-api"
exec java $JAVA_OPTS -jar /app/app.jar


