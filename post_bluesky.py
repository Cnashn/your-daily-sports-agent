import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

BSKY_HOST = "https://bsky.social"
POST_LIMIT = 300
SUFFIX_RESERVE = 8


def load_entry():
    today = datetime.now(timezone.utc).date()
    path = Path("journal") / f"{today.strftime('%y-%m-%d')}.md"
    if not path.exists():
        return None, None
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    header = ""
    if lines and lines[0].startswith("#"):
        header = lines[0].lstrip("# ").strip()
        lines = lines[1:]
    return header, "\n".join(lines).strip()


def split_chunks(text, limit, first_limit=None):
    sentences = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            sentences.extend(re.split(r"(?<=[.!?])\s+", paragraph))

    chunks = []
    current = ""
    for sentence in sentences:
        cap = first_limit if not chunks and first_limit else limit
        while len(sentence) > cap:
            head, sentence = sentence[: cap - 1] + "…", "…" + sentence[cap - 1 :]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
            cap = limit
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= cap:
            current = candidate
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def build_posts(header, body):
    limit = POST_LIMIT - SUFFIX_RESERVE
    first_limit = limit - len(header) - 2 if header else None
    chunks = split_chunks(body, limit, first_limit)
    if header:
        chunks[0] = f"{header}\n\n{chunks[0]}"
    if len(chunks) == 1:
        return chunks
    return [f"{chunk} ({i}/{len(chunks)})" for i, chunk in enumerate(chunks, 1)]


def create_session(handle, password):
    resp = requests.post(
        f"{BSKY_HOST}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["accessJwt"], data["did"]


def post_thread(posts, jwt, did):
    root = None
    parent = None
    for text in posts:
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
    handle = os.environ.get("BLUESKY_HANDLE")
    password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not password:
        print("Bluesky secrets not set, skipping post.")
        return

    header, body = load_entry()
    if not body:
        print("No journal entry for today, skipping post.")
        return

    posts = build_posts(header, body)
    jwt, did = create_session(handle, password)
    root = post_thread(posts, jwt, did)
    print(f"Posted {len(posts)} posts, thread root: {root['uri']}")


if __name__ == "__main__":
    main()
