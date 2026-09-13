"""Run a Python file inside the Blender that has the blender-mcp add-on's server on.

    python mcp_exec.py <code.py> [timeout seconds] [host:port]
    python mcp_exec.py - < snippet.py

The add-on (Blender sidebar > BlenderMCP > "Connect to MCP server") listens on
127.0.0.1:9876 and executes ``execute_code`` requests on Blender's main thread,
so the snippet sees the live scene and the UI updates when it returns.  Whatever
the snippet prints comes back as the result and is printed here; an exception
inside Blender comes back as an error message.  See docs/blender-mcp-driving.md.
"""
import io
import json
import socket
import sys


def send(command, host="127.0.0.1", port=9876, timeout=300.0):
    """One request, one JSON reply (the server closes nothing; read until the
    reply parses)."""
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.sendall(json.dumps(command).encode("utf-8"))
    buf = b""
    while True:
        chunk = sock.recv(1 << 16)
        if not chunk:
            break
        buf += chunk
        try:
            json.loads(buf.decode("utf-8"))
            break
        except ValueError:
            continue
    sock.close()
    return json.loads(buf.decode("utf-8"))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
    host, port = "127.0.0.1", 9876
    if len(sys.argv) > 3:
        host, port = sys.argv[3].split(":")
        port = int(port)
    code = sys.stdin.read() if src == "-" else io.open(src, encoding="utf-8").read()
    reply = send({"type": "execute_code", "params": {"code": code}}, host, port, timeout)
    if reply.get("status") != "success":
        print("blender error:", reply.get("message") or reply)
        raise SystemExit(1)
    result = reply.get("result", {})
    output = result.get("result") if isinstance(result, dict) else result
    print(output if isinstance(output, str) else json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
