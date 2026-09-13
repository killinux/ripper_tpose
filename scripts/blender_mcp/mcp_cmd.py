"""Send any blender-mcp command and print the JSON reply.

    python mcp_cmd.py get_scene_info
    python mcp_cmd.py get_viewport_screenshot '{"max_size": 1100, "filepath": "C:/tmp/view.png"}'
    python mcp_cmd.py get_object_info '{"name": "Pc B14 Outfit1 Hd_arm"}'

Commands the add-on answers (its ``_execute_command_internal`` handler table):
get_scene_info, get_object_info, get_viewport_screenshot, execute_code, plus
the Poly Haven / Sketchfab / Hyper3D ones when those integrations are enabled.
"""
import json
import sys

from mcp_exec import send


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    reply = send({"type": sys.argv[1], "params": params}, timeout=120.0)
    print(json.dumps(reply, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
