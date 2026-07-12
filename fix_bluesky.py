import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

from post_bluesky import BSKY_HOST, build_posts, create_session

DELETE_RKEYS = [
    "3mqbtzj7m6t24",
    "3mqbtzjpbtu2p",
    "3mqbtzk25jb2p",
    "3mqbtzkjrnl22",
    "3mqbtzkqtub2i",
    "3mqbtzl4ziz2i",
    "3mqbtzljjvj2i",
    "3mqe6wqyurz2s",
    "3mqe6wrg2tg2f",
    "3mqe6wrm4c72i",
    "3mqe6wry3v222",
    "3mqe6ws6uro2f",
    "3mqe6wsllyw2f",
    "3mqe6wt3nrp2i",
    "3mqe6wt6t7z2c",
    "3mqgqm67bfy2d",
    "3mqgqm6ghqg26",
    "3mqgqm6neqv2v",
    "3mqgqm6q7mp2i",
    "3mqgqm6xkhf2p",
    "3mqgqm72mmx2i",
    "3mqgqm75xrx2q",
]

REPOSTS = [
    ("journal/26-07-10.md", "2026-07-10T09:40:00Z"),
    ("journal/26-07-11.md", "2026-07-11T08:00:00Z"),
    ("journal/26-07-12.md", "2026-07-12T08:25:00Z"),
]


def load_entry(path):
    lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
    header = ""
    if lines and lines[0].startswith("#"):
        header = lines[0].lstrip("# ").strip()
        lines = lines[1:]
    return header, "\n".join(lines).strip()


def delete_post(jwt, did, rkey):
    resp = requests.post(
        f"{BSKY_HOST}/xrpc/com.atproto.repo.deleteRecord",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"repo": did, "collection": "app.bsky.feed.post", "rkey": rkey},
        timeout=30,
    )
    resp.raise_for_status()


def post_thread_at(posts, jwt, did, base_time):
    base = datetime.strptime(base_time, "%Y-%m-%dT%H:%M:%SZ")
    root = None
    parent = None
    for i, text in enumerate(posts):
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": (base + timedelta(seconds=i * 10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "langs": ["en"],
        }
        if parent:
            record["reply"] = {"root": root, "parent": parent}
        resp = requests.post(
            f"{BSKY_HOST}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
            timeout=30,
        )
        resp.raise_for_status()
        ref = {"uri": resp.json()["uri"], "cid": resp.json()["cid"]}
        if root is None:
            root = ref
        parent = ref
    return root


def main():
    handle = os.environ["BLUESKY_HANDLE"]
    password = os.environ["BLUESKY_APP_PASSWORD"]
    jwt, did = create_session(handle, password)

    for rkey in DELETE_RKEYS:
        delete_post(jwt, did, rkey)
        print(f"deleted {rkey}")

    for path, base_time in REPOSTS:
        header, body = load_entry(path)
        posts = build_posts(header, body)
        root = post_thread_at(posts, jwt, did, base_time)
        print(f"reposted {path} as {len(posts)} posts, root {root['uri']}")


if __name__ == "__main__":
    main()
