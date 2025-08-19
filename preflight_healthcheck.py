import os
import sys
import time
import json
import subprocess
import urllib.request
import contextlib
import signal


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(project_root, "main", "xiaozhi-server")

    env = os.environ.copy()
    env["RAILWAY_PROJECT_ID"] = env.get("RAILWAY_PROJECT_ID", "local-preflight")
    env["PORT"] = env.get("PORT", "8000")

    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=app_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    base = f"http://127.0.0.1:{env['PORT']}"
    url = f"{base}/xiaozhi/ota/"

    ok = False
    start = time.time()
    try:
        for _ in range(120):  # up to ~60s
            time.sleep(0.5)
            try:
                with contextlib.closing(urllib.request.urlopen(url, timeout=1.5)) as r:
                    if r.status == 200:
                        body = r.read().decode("utf-8", "ignore")
                        json.loads(body)
                        ok = True
                        break
            except Exception:
                pass
    finally:
        # terminate app
        with contextlib.suppress(Exception):
            if os.name == "nt":
                proc.terminate()
            else:
                os.kill(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()

    if ok:
        elapsed = time.time() - start
        print(f"HEALTHCHECK OK in {elapsed:.1f}s -> {url}")
        sys.exit(0)
    else:
        # print last 200 lines of output
        try:
            output = proc.stdout.read() if proc.stdout else ""
            lines = output.splitlines()[-200:]
            print("--- app output (tail) ---")
            print("\n".join(lines))
        except Exception:
            pass
        print(f"HEALTHCHECK FAILED for {url}")
        sys.exit(1)


if __name__ == "__main__":
    main()


