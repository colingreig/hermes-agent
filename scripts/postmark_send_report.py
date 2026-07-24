#!/usr/bin/env python3
"""
postmark_send_report.py — send a plain-text status email via Postmark.

Built for the hermes-self-report cron (6-hourly Hermes status digest to Colin),
but generic enough for any script/skill that needs to send a simple transactional
email through the account's existing Postmark server.

Reuses the SAME server token ignite-workbench uses to send from
sales@ignitemarketing.com (see lib/notify/postmark.ts in that repo) — no new
credentials. Requires POSTMARK_SERVER_TOKEN in the environment (1Password-injected
via op-env.sh / op-secrets.env; Doppler decommissioned 2026-07-03).

Usage:
  python3 ~/.hermes/scripts/postmark_send_report.py \
    --to colin@colingreig.com \
    --subject "Hermes status — 2026-07-01 12:00" \
    --body-file /path/to/body.txt
  # or pipe the body on stdin:
  echo "body text" | python3 ~/.hermes/scripts/postmark_send_report.py --to ... --subject ...

Exit codes: 0 sent, 1 send/config error, 2 usage error.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

DEFAULT_FROM = "Hermes <sales@ignitemarketing.com>"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body-file", help="Path to a text file with the plain-text email body. Omit to read stdin.")
    p.add_argument("--html-file", help="Optional path to an HTML body. When given, the email is "
                                       "multipart (HtmlBody + TextBody); the text body is the plain-text fallback.")
    p.add_argument("--from-addr", default=DEFAULT_FROM)
    p.add_argument("--tag", default="hermes-self-report")
    args = p.parse_args()

    token = None
    try:
        from agent import lazy_secret_resolver
        token = lazy_secret_resolver.get("POSTMARK_SERVER_TOKEN")
    except Exception:
        token = None
    if not token:
        token = os.environ.get("POSTMARK_SERVER_TOKEN")
    if not token:
        print("ERROR: POSTMARK_SERVER_TOKEN not set — check 1Password op-secrets.env", file=sys.stderr)
        return 1

    if args.body_file:
        with open(args.body_file, "r") as f:
            body = f.read()
    else:
        body = sys.stdin.read()

    payload = {
        "From": args.from_addr,
        "To": args.to,
        "Subject": args.subject,
        "TextBody": body,
        "MessageStream": "outbound",
        "Tag": args.tag,
    }

    if args.html_file:
        with open(args.html_file, "r") as f:
            payload["HtmlBody"] = f.read()

    req = urllib.request.Request(
        "https://api.postmarkapp.com/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": token,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(json.dumps({"status": "sent", "message_id": result.get("MessageID")}))
            return 0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(json.dumps({"status": "error", "http_code": e.code, "detail": detail}), file=sys.stderr)
        return 1
    except Exception as e:
        print(json.dumps({"status": "error", "detail": str(e)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
