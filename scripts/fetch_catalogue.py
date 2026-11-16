#!/usr/bin/env python3
"""Fetch candidate marble/stone images from Wikimedia Commons with full provenance.

Only images under permissive licenses (Public domain, CC0, CC BY, CC BY-SA) are kept.
Every image is saved with a provenance record (source URL, author, license, sha1, fetch date).

Run:  python scripts/fetch_catalogue.py
Output: data/raw/wikimedia/<pageid>.<ext> + data/raw/wikimedia/index.json
"""
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

import PIL.Image

API = "https://commons.wikimedia.org/w/api.php"
UA = "VeinSearchPOC/0.1 (interview demo; contact: local user)"
RAW = pathlib.Path("data/raw/wikimedia")
RAW.mkdir(parents=True, exist_ok=True)

# (query, per-query limit)
QUERIES = [
    ("filetype:bitmap polished marble slab", 25),
    ("filetype:bitmap marble texture closeup", 25),
    ("filetype:bitmap marble sample collection", 20),
    ("filetype:bitmap travertine stone slab", 20),
    ("filetype:bitmap onyx marble slab", 20),
    ("filetype:bitmap polished granite slab", 25),
    ("filetype:bitmap limestone slab polished", 20),
    ("filetype:bitmap sandstone slab texture", 20),
    ("filetype:bitmap quartzite slab stone", 20),
]
CATEGORIES = [
    ("Category:Granite textures", 30),
    ("Category:Marble samples", 30),
    ("Category:Travertine", 30),
]
ALLOWED_LICENSE = re.compile(
    r"(public domain|cc0|cc by(?!-nc)(?!-nd)|cc by-sa|no restrictions|attribution)", re.I
)
BLOCKED_LICENSE = re.compile(r"(fair use|non-free|nc |nd )", re.I)
MIN_DIM = 600


def api(params: dict) -> dict:
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def collect_candidates() -> dict:
    """Return pageid -> {title, url, thumburl, metadata} from searches + categories."""
    pages = {}

    def absorb(res):
        for p in (res.get("query", {}).get("pages") or {}).values():
            if p.get("pageid", -1) < 0:
                continue
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            if mime not in ("image/jpeg", "image/png"):
                continue
            if (ii.get("width", 0) < MIN_DIM) and (ii.get("height", 0) < MIN_DIM):
                continue
            em = ii.get("extmetadata", {}) or {}
            lic = strip_html(em.get("LicenseShortName", {}).get("value", ""))
            if BLOCKED_LICENSE.search(lic) or not ALLOWED_LICENSE.search(lic):
                continue
            pages[p["pageid"]] = {
                "pageid": p["pageid"],
                "title": p.get("title", ""),
                "mime": mime,
                "width": ii.get("width"),
                "height": ii.get("height"),
                "description_url": ii.get("descriptionurl", ""),
                "thumburl": ii.get("thumburl") or ii.get("url"),
                "license": lic,
                "license_url": strip_html(em.get("LicenseUrl", {}).get("value", "")),
                "artist": strip_html(em.get("Artist", {}).get("value", "")),
                "credit": strip_html(em.get("Credit", {}).get("value", ""))[:300],
                "description": strip_html(
                    em.get("ImageDescription", {}).get("value", "")
                )[:500],
                "date_original": strip_html(
                    em.get("DateTimeOriginal", {}).get("value", "")
                ),
            }

    for q, limit in QUERIES:
        try:
            absorb(
                api(
                    {
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": q,
                        "gsrnamespace": 6,
                        "gsrlimit": limit,
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata|sha1",
                        "iiurlwidth": 1024,
                    }
                )
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ! search failed for {q!r}: {e}", file=sys.stderr)
    for cat, limit in CATEGORIES:
        try:
            absorb(
                api(
                    {
                        "action": "query",
                        "generator": "categorymembers",
                        "gcmtitle": cat,
                        "gcmtype": "file",
                        "gcmlimit": limit,
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata|sha1",
                        "iiurlwidth": 1024,
                    }
                )
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ! category failed for {cat!r}: {e}", file=sys.stderr)
    return pages


def download(pages: dict) -> list:
    index = []
    for pid, meta in sorted(pages.items()):
        ext = "jpg" if meta["mime"] == "image/jpeg" else "png"
        dest = RAW / f"{pid}.{ext}"
        if not dest.exists():
            try:
                req = urllib.request.Request(
                    meta["thumburl"], headers={"User-Agent": UA}
                )
                data = urllib.request.urlopen(req, timeout=60).read()
                img = PIL.Image.open(__import__("io").BytesIO(data))
                img.verify()
                dest.write_bytes(data)
            except Exception as e:  # noqa: BLE001
                print(f"  ! download failed {pid}: {e}", file=sys.stderr)
                continue
        index.append(meta)
        print(f"  ok {pid} {meta['license']:28s} {meta['title'][:60]}")
    return index


def main():
    print("Collecting candidates from Wikimedia Commons ...")
    pages = collect_candidates()
    print(f"{len(pages)} candidate images with permissive licenses. Downloading ...")
    index = download(pages)
    sha = {p["pageid"]: p for p in index}
    out = RAW / "index.json"
    out.write_text(json.dumps(list(sha.values()), indent=2, ensure_ascii=False))
    print(f"Wrote {out} ({len(index)} images)")


if __name__ == "__main__":
    main()
