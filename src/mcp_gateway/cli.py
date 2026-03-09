"""mcp-gw - Thin CLI client for MCP Gateway REST API."""

import argparse
import json
import sys

import httpx

DEFAULT_GATEWAY = "http://localhost:8085"


def get_gateway_url(args):
    """Resolve gateway URL from flag, env, or default."""
    import os

    if args.gateway:
        return args.gateway.rstrip("/")
    return os.environ.get("MCP_GATEWAY_URL", DEFAULT_GATEWAY).rstrip("/")


def request(url, method="GET", json_data=None, timeout=30.0):
    """Make HTTP request, handle errors."""
    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "POST":
                r = client.post(url, json=json_data or {})
            else:
                r = client.get(url)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        print(f"Error: cannot connect to gateway at {url}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        print(f"Error: {detail}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    """List servers and their tools."""
    base = get_gateway_url(args)
    servers = request(f"{base}/api/servers")

    if args.json:
        print(json.dumps(servers, indent=2))
        return

    for s in servers:
        status = s["status"]
        tool_count = len(s.get("tools", []))
        print(f"{s['id']}  {status}  {tool_count} tools")


def cmd_info(args):
    """Show server tools or specific tool schema."""
    base = get_gateway_url(args)

    if args.tool:
        schema = request(f"{base}/api/tools/{args.server}/{args.tool}")
        if args.json:
            print(json.dumps(schema, indent=2))
        else:
            print(f"{schema['name']}")
            if schema.get("description"):
                print(f"  {schema['description']}")
            print()
            print(json.dumps(schema.get("input_schema", {}), indent=2))
    else:
        server = request(f"{base}/api/servers/{args.server}")
        if args.json:
            print(json.dumps(server, indent=2))
        else:
            print(f"{server['id']}  {server['status']}")
            for tool in server.get("tools", []):
                print(f"  {tool}")


def cmd_call(args):
    """Call a tool."""
    base = get_gateway_url(args)

    # Parse arguments: inline JSON, stdin, or empty
    if args.arguments == "-":
        raw = sys.stdin.read()
        tool_args = json.loads(raw) if raw.strip() else {}
    elif args.arguments:
        tool_args = json.loads(args.arguments)
    else:
        tool_args = {}

    result = request(
        f"{base}/api/tools/{args.server}/{args.tool}",
        method="POST",
        json_data=tool_args,
        timeout=60.0,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if not result.get("success"):
        print(f"Error: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

    # Extract text from MCP content blocks
    content = result.get("result", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                print(item["text"])
    elif content is not None:
        print(json.dumps(content, indent=2))


def cmd_grep(args):
    """Search tools by name."""
    base = get_gateway_url(args)
    tools = request(f"{base}/api/tools?search={args.pattern}")

    if args.json:
        print(json.dumps(tools, indent=2))
        return

    for t in tools:
        print(f"{t['server_id']}/{t['name']}  {t.get('description', '')}")


def main():
    parser = argparse.ArgumentParser(
        prog="mcp-gw",
        description="CLI client for MCP Gateway",
    )
    parser.add_argument(
        "--gateway", help="Gateway URL (default: $MCP_GATEWAY_URL or localhost:8085)"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List servers and tools")

    p_info = sub.add_parser("info", help="Show server or tool details")
    p_info.add_argument("server", help="Server ID")
    p_info.add_argument("tool", nargs="?", help="Tool name (optional)")

    p_call = sub.add_parser("call", help="Call a tool")
    p_call.add_argument("server", help="Server ID")
    p_call.add_argument("tool", help="Tool name")
    p_call.add_argument(
        "arguments", nargs="?", help="JSON arguments (or '-' for stdin)"
    )

    p_grep = sub.add_parser("grep", help="Search tools by name")
    p_grep.add_argument("pattern", help="Search pattern")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"list": cmd_list, "info": cmd_info, "call": cmd_call, "grep": cmd_grep}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
