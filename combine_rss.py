#!/usr/bin/env python3
import feedparser
import requests
import email.utils
from time import mktime
from datetime import datetime, timezone
from xml.dom.minidom import Document, parseString
from xml.parsers.expat import ExpatError
import os

RSS_URLS = [
    "https://www.ft.com/stream/82645c31-4426-4ef5-99c9-9df6e0940c00?format=rss"
]

ARCHIVE_PREFIX = "https://archive.is/o/ggFl1/"
OUTPUT_FILE = "combined.xml"
MAX_ENTRIES = 500
MEDIA_NS = "http://search.yahoo.com/mrss/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.ft.com/",
    "Cache-Control": "no-cache",
}

def fetch_feed(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "html" in content_type and "xml" not in content_type:
            print(f"⚠️  Got HTML instead of XML from {url}")
            print(f"   Content-Type: {content_type}")
            print(f"   Response snippet: {resp.text[:300]}")
            return None
        return feedparser.parse(resp.content)
    except requests.RequestException as e:
        print(f"⚠️  HTTP error fetching {url}: {e}")
        return None

def parse_entry_datetime(entry):
    for field in ("published_parsed", "updated_parsed"):
        val = entry.get(field)
        if val:
            return datetime.fromtimestamp(mktime(val), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)

def get_thumbnail(entry):
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")
    if hasattr(entry, "media_content") and entry.media_content:
        for mc in entry.media_content:
            if mc.get("medium") == "image" or mc.get("type", "").startswith("image/"):
                return mc.get("url", "")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href", "") or enc.get("url", "")
    return ""

def load_existing_entries(filepath):
    """Read existing combined.xml and return list of entry dicts keyed by guid."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "rb") as f:
            dom = parseString(f.read())
    except ExpatError:
        print("⚠️  Existing file could not be parsed, starting fresh.")
        return {}

    entries = {}
    for item in dom.getElementsByTagName("item"):
        def text(tag):
            els = item.getElementsByTagName(tag)
            return els[0].firstChild.nodeValue.strip() if els and els[0].firstChild else ""

        guid = text("guid")
        if not guid:
            continue
        pub = text("pubDate")
        try:
            dt = datetime(*email.utils.parsedate(pub)[:6], tzinfo=timezone.utc) if pub else datetime.now(tz=timezone.utc)
        except Exception:
            dt = datetime.now(tz=timezone.utc)

        thumbnail = ""
        thumb_nodes = item.getElementsByTagName("media:thumbnail")
        if thumb_nodes:
            thumbnail = thumb_nodes[0].getAttribute("url")

        entries[guid] = {
            "title":        text("title"),
            "orig_link":    guid,
            "archive_link": text("link"),
            "summary":      text("description"),
            "published_dt": dt,
            "thumbnail":    thumbnail,
        }
    return entries

def build_xml(entries):
    doc = Document()
    rss = doc.createElement("rss")
    rss.setAttribute("version", "2.0")
    rss.setAttribute("xmlns:media", MEDIA_NS)
    doc.appendChild(rss)

    channel = doc.createElement("channel")
    rss.appendChild(channel)
    channel.appendChild(doc.createElement("title")).appendChild(doc.createTextNode("FT World Archive Feed"))
    channel.appendChild(doc.createElement("link")).appendChild(doc.createTextNode("https://www.ft.com/world"))
    channel.appendChild(doc.createElement("description")).appendChild(doc.createTextNode("FT World feed with archive links"))

    for it in entries:
        item_el = doc.createElement("item")
        channel.appendChild(item_el)
        item_el.appendChild(doc.createElement("title")).appendChild(doc.createTextNode(it["title"]))
        item_el.appendChild(doc.createElement("link")).appendChild(doc.createTextNode(it["archive_link"]))
        item_el.appendChild(doc.createElement("guid")).appendChild(doc.createTextNode(it["orig_link"]))
        item_el.appendChild(doc.createElement("description")).appendChild(doc.createTextNode(it["summary"]))
        item_el.appendChild(doc.createElement("pubDate")).appendChild(
            doc.createTextNode(email.utils.format_datetime(it["published_dt"]))
        )
        if it.get("thumbnail"):
            thumb_el = doc.createElementNS(MEDIA_NS, "media:thumbnail")
            thumb_el.setAttribute("url", it["thumbnail"])
            item_el.appendChild(thumb_el)
    return doc

def main():
    # 1. Load existing entries (keyed by orig_link/guid for dedup)
    existing = load_existing_entries(OUTPUT_FILE)
    print(f"ℹ️  Loaded {len(existing)} existing entries from {OUTPUT_FILE}")

    # 2. Fetch new entries from feeds
    new_count = 0
    for feed_url in RSS_URLS:
        feed = fetch_feed(feed_url)
        if feed is None:
            continue
        if feed.bozo and not feed.entries:
            print(f"⚠️  Failed to parse: {feed_url} — {feed.bozo_exception}")
            continue
        print(f"ℹ️  {feed_url} → {len(feed.entries)} entries fetched")
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in existing:
                continue
            existing[link] = {
                "title":        entry.get("title", "Untitled"),
                "orig_link":    link,
                "archive_link": ARCHIVE_PREFIX + link,
                "summary":      entry.get("summary") or entry.get("description") or "",
                "published_dt": parse_entry_datetime(entry),
                "thumbnail":    get_thumbnail(entry),
            }
            new_count += 1

    print(f"ℹ️  {new_count} new entries added")

    # 3. Sort newest first
    all_entries = sorted(existing.values(), key=lambda x: x["published_dt"], reverse=True)

    # 4. Recycle: keep only the newest MAX_ENTRIES
    if len(all_entries) > MAX_ENTRIES:
        dropped = len(all_entries) - MAX_ENTRIES
        all_entries = all_entries[:MAX_ENTRIES]
        print(f"ℹ️  Recycled {dropped} oldest entries (cap: {MAX_ENTRIES})")

    # 5. Write output
    doc = build_xml(all_entries)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(doc.toxml(encoding="utf-8"))

    print(f"✅ {OUTPUT_FILE} written with {len(all_entries)} entries.")

if __name__ == "__main__":
    main()
