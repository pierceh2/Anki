"""Download a read-only copy of your collection from AnkiWeb and write today's
due counts to counts.json.

Never uploads: the local collection is a throwaway copy, and the only sync
action ever taken is a full DOWNLOAD, so your real collection can't be touched.

Env vars: ANKIWEB_USER, ANKIWEB_PASS
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from anki.collection import Collection

OUT = Path("counts.json")


def build_counts(col):
    tree = col.sched.deck_due_tree()
    decks = []
    for node in tree.children:  # top-level decks; counts include subdecks
        decks.append(
            {
                "name": node.name,
                "new": node.new_count,
                "learn": node.learn_count,
                "review": node.review_count,
            }
        )
    return {
        "new": sum(d["new"] for d in decks),
        "learn": sum(d["learn"] for d in decks),
        "review": sum(d["review"] for d in decks),
        "total_due": sum(d["new"] + d["learn"] + d["review"] for d in decks),
        "decks": decks,
    }


def main():
    user = os.environ["ANKIWEB_USER"]
    password = os.environ["ANKIWEB_PASS"]

    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(os.path.join(tmp, "collection.anki2"))
        try:
            auth = col.sync_login(username=user, password=password, endpoint=None)
            out = col.sync_collection(auth, sync_media=False)
            if out.new_endpoint:
                auth.endpoint = out.new_endpoint

            # Fresh empty collection -> server asks for a full download.
            if out.required in (out.FULL_DOWNLOAD, out.FULL_SYNC):
                col.close_for_full_sync()
                col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
                col.reopen(after_full_sync=True)
            elif out.required == out.FULL_UPLOAD:
                sys.exit("Server wanted an upload; refusing (read-only script).")

            counts = build_counts(col)
        finally:
            col.close()

    # Only rewrite the file (and so only create a commit) when counts change.
    if OUT.exists():
        old = json.loads(OUT.read_text())
        old.pop("updated", None)
        if old == counts:
            print("No change.")
            return

    counts["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(counts, indent=2) + "\n")
    print(f"Wrote {OUT}: {counts['total_due']} due")


if __name__ == "__main__":
    main()