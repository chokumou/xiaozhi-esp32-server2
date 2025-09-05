#!/bin/sh
# Usage: put .env.manager-api next to this script or edit path
ENVFILE="$(dirname "$0")/../.env.manager-api"

if [ ! -f "$ENVFILE" ]; then
  echo "Env file not found: $ENVFILE"
  exit 1
fi

echo "Reading $ENVFILE"
set -o allexport
. "$ENVFILE"
set +o allexport

if ! command -v railway >/dev/null 2>&1; then
  echo "railway CLI not found. Install from https://railway.app/docs/cli" >&2
  exit 1
fi

echo "Setting Railway variables from $ENVFILE"
# iterate lines
grep -v '^\s*#' "$ENVFILE" | grep -E '=' | while IFS='=' read -r key value; do
  # trim
  key=$(echo "$key" | sed 's/\s*$//;s/^\s*//')
  value=$(echo "$value" | sed 's/^"\(.*\)"$\1/;s/^\s*//;s/\s*$//')
  echo "railway variables set $key --value '"$value"'"
  railway variables set "$key" --value "$value"
done

echo "Done"



