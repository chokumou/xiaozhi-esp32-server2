#!/usr/bin/env python3
"""Simple websocket device emulator for local testing.

Usage:
  python emulate_device_ws.py --url ws://localhost:8090/ws --device-id test-device --token <JWT>

This script will:
 - connect to the server
 - send a hello JSON including the token
 - send a text message that includes the trigger word to test memory save/query
"""
import argparse
import asyncio
import json

try:
    import websockets
except Exception:
    print("Please install websockets: pip install websockets")
    raise


async def run(uri, device_id, token, message):
    async with websockets.connect(uri) as ws:
        hello = {
            "type": "hello",
            "mac": device_id,
            "device_id": device_id,
            "token": token,
            "audio_params": {"format": "pcm"},
        }
        await ws.send(json.dumps(hello))
        print("Sent hello")
        # read welcome
        try:
            welcome = await asyncio.wait_for(ws.recv(), timeout=5)
            print("Welcome:", welcome)
        except asyncio.TimeoutError:
            print("No welcome received")

        # send a text message (server's text handler will process and may trigger memory)
        await ws.send(message)
        print("Sent message:", message)

        # wait some seconds for server processing and logs
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            print("Server response:", resp)
        except asyncio.TimeoutError:
            print("No immediate response")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="ws://localhost:8090/ws")
    p.add_argument("--device-id", default="test-device")
    p.add_argument("--token", default="")
    p.add_argument("--message", default="記憶 私の好きな色は青です")
    args = p.parse_args()
    asyncio.run(run(args.url, args.device_id, args.token, args.message))


if __name__ == "__main__":
    main()


