#!/bin/sh
set -e

echo "=== ENTRYPOINT.SH STARTING ==="
echo "Timestamp: $(date)"
echo "PWD: $(pwd)"
echo "USER: $(whoami)"

# Safety checks
if ! command -v python >/dev/null 2>&1; then
    echo "ERROR: Python not found in PATH"
    exit 1
fi

echo "Python version: $(python --version)"
echo "Files in current directory:"
ls -la || echo "ls failed"

# Generate runtime config from environment variables if not provided
echo "Creating data directory..."
mkdir -p "$(pwd)/data" || {
    echo "ERROR: Failed to create data directory"
    exit 1
}

CONFIG_PATH="$(pwd)/data/.config.yaml"
echo "Generating runtime config to ${CONFIG_PATH}"
cat > "${CONFIG_PATH}" <<EOF
manager-api:
  url: "${MANAGER_API_URL:-}"
  secret: "${MANAGER_API_SECRET:-}"
selected_module:
  Memory: ${MEMORY_MODULE:-nomem}
QUICK_SAVE: "${QUICK_SAVE:-0}"
EOF

echo "Runtime config:" 
sed -n '1,120p' "${CONFIG_PATH}"

echo "=== Environment Variables Debug ==="
echo "MANAGER_API_URL: '${MANAGER_API_URL:-UNSET}'"
echo "MANAGER_API_SECRET: '${MANAGER_API_SECRET:-UNSET}'"
echo "MEMORY_MODULE: '${MEMORY_MODULE:-UNSET}'"
echo "QUICK_SAVE: '${QUICK_SAVE:-UNSET}'"
echo "=== End Environment Variables ==="

# Execute the original command
echo "--- ENTRYPOINT DEBUG: start ---"
echo "PWD: $(pwd)"
echo "Files:" && ls -la || true
echo "PYTHONPATH before export: $PYTHONPATH"
export PYTHONPATH="$(pwd):$PYTHONPATH"
echo "PYTHONPATH after export: $PYTHONPATH"
echo "Python sys.path and import test:" 
python - <<'PY'
import sys, os
print('cwd:', os.getcwd())
print('sys.path:')
print('\n'.join(sys.path))
try:
    import config.config_loader as _cl
    print('import config.config_loader: OK')
except Exception as e:
    print('import config.config_loader: ERROR ->', repr(e))
try:
    import webrtcvad
    print('import webrtcvad: OK')
except Exception as e:
    print('import webrtcvad: ERROR ->', repr(e))
PY
echo "--- ENTRYPOINT DEBUG: end ---"

echo "Starting Python application..."
if [ -f "app.py" ]; then
    echo "app.py found, executing..."
    exec python app.py
else
    echo "ERROR: app.py not found in $(pwd)"
    echo "Available Python files:"
    find . -name "*.py" -maxdepth 2
    exit 1
fi

#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="/opt/models/sherpa_sense_voice"
MODEL_ONNX="$MODEL_DIR/model.int8.onnx"
TOKENS_TXT="$MODEL_DIR/tokens.txt"

mkdir -p "$MODEL_DIR"

ensure_models() {
	if [ -s "$MODEL_ONNX" ] && [ -s "$TOKENS_TXT" ]; then
		echo "[entrypoint] Models already present in $MODEL_DIR"
		return 0
	fi

	echo "[entrypoint] Models missing. Attempting download into $MODEL_DIR ..."

	# Multiple mirrors with retries
	onnx_urls=(
		"https://huggingface.co/pdzsonline/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/main/model.int8.onnx?download=true"
		"https://raw.githubusercontent.com/pdzsonline/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/main/model.int8.onnx"
	)
	tokens_urls=(
		"https://huggingface.co/pdzsonline/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/main/tokens.txt?download=true"
		"https://raw.githubusercontent.com/pdzsonline/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/main/tokens.txt"
	)

	for attempt in {1..5}; do
		echo "[entrypoint] Download attempt $attempt ..."
		# ONNX
		for u in "${onnx_urls[@]}"; do
			if curl -fL --retry 5 --retry-delay 2 -o "$MODEL_ONNX.part" "$u"; then
				break
			fi
			sleep 1
		done
		# TOKENS
		for u in "${tokens_urls[@]}"; do
			if curl -fL --retry 5 --retry-delay 2 -o "$TOKENS_TXT.part" "$u"; then
				break
			fi
			sleep 1
		done

		if [ -s "$MODEL_ONNX.part" ] && [ -s "$TOKENS_TXT.part" ]; then
			mv -f "$MODEL_ONNX.part" "$MODEL_ONNX"
			mv -f "$TOKENS_TXT.part" "$TOKENS_TXT"
			echo "[entrypoint] Model files downloaded successfully."
			return 0
		fi
		echo "[entrypoint] Attempt $attempt failed; will retry."
		rm -f "$MODEL_ONNX.part" "$TOKENS_TXT.part" || true
		sleep 2
	done

	echo "[entrypoint] WARNING: Failed to download models after multiple attempts. The server will start; ASR may not initialize until models are present."
	return 1
}

# If Railway Volume is attached at /opt/models, this runs only once per volume
ensure_models || true

exec python app.py



