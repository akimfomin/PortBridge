"""Join a private PortBridge discussion and follow its updates."""

import argparse
import json
import os
from uuid import uuid4

from .discussion import MAX_WAIT_SECONDS
from .exchange_client import ExchangeClient


def watch(client, cursor):
    """Keep a request waiting for the next subscribed update."""
    while True:
        page = client.request("updates", query={"after": cursor, "wait_seconds": MAX_WAIT_SECONDS})
        for event in page["events"]:
            print(json.dumps(event, ensure_ascii=True), flush=True)
        cursor = page["next_cursor"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange-port", type=int, default=8765)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("join", "leave", "thread", "coordination"):
        commands.add_parser(name).add_argument("problem_id")
    send = commands.add_parser("send")
    send.add_argument("problem_id")
    send.add_argument("text")
    send.add_argument("--source-url")
    send.add_argument("--reply-to", type=int)
    send.add_argument("--client-id", help="reuse an earlier message key for an exact retry")
    follow = commands.add_parser("watch")
    follow.add_argument("--after", type=int, default=0, help="last processed update ID")
    args = parser.parse_args(argv)
    try:
        client = ExchangeClient(args.exchange_port, os.environ.get("PORTBRIDGE_EXCHANGE_TOKEN"))
        if args.command == "watch":
            watch(client, args.after)
            return
        if args.command in {"join", "leave"}:
            result = client.request("subscribe", body={"problem_id": args.problem_id, "enabled": args.command == "join"})
        elif args.command == "send":
            body = {"problem_id": args.problem_id, "text": args.text, "client_id": args.client_id or uuid4().hex}
            if args.source_url is not None:
                body["source_url"] = args.source_url
            if args.reply_to is not None:
                body["reply_to"] = args.reply_to
            result = client.request("message", body=body)
        else:
            result = client.request(args.command, query={"problem_id": args.problem_id})
    except KeyboardInterrupt:
        return
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
