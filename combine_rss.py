#!/usr/bin/env python3
import feedparser
import requests
import email.utils
from time import mktime
from datetime import datetime, timezone
from xml.dom.minidom import Document

RSS_URLS = [
    "https://www.ft.com/stream/82645c31-4426-4ef5-99c9-9df6e0940c00?format=rss"
]

ARCHIVE_PREFIX = "https://archive.is/o/ggFl1/"
OUTPUT_FILE = "combined.xml"

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

def main():
    doc = Document()
    rss = doc.createElement("rss")
    rss.setAttribute("version", "2.0")
    doc.appendChild(rss)

    channel = doc.createElement("channel")
    rss.appendChild(channel)
    channel.appendChild(doc.createElement("title")).appendChild(doc.createTextNode("FT World Archive Feed"))
    channel.appendChild(doc.createElement("link")).appendChild(doc.createTextNode("https://www.ft.com/world"))
    channel.appendChild(doc.createElement("description")).appendChild(doc.createTextNode("FT World feed with archive links"))

    all_entries = []

    for feed_url in RSS_URLS:
        feed = fetch_feed(feed_url)
        if feed is None:
            continue
        if feed.bozo and not feed.entries:
            print(f"⚠️  Failed to parse: {feed_url} — {feed.bozo_exception}")
            continue
        print(f"ℹ️  {feed_url} → {len(feed.entries)} entries")
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue
            all_entries.append({
                "title":        entry.get("title", "Untitled"),
                "orig_link":    link,
                "archive_link": ARCHIVE_PREFIX + link,
                "summary":      entry.get("summary") or entry.get("description") or "",
                "published_dt": parse_entry_datetime(entry)
            })

    all_entries.sort(key=lambda x: x["published_dt"], reverse=True)

    for it in all_entries:
        item_el = doc.createElement("item")
        channel.appendChild(item_el)
        item_el.appendChild(doc.createElement("title")).appendChild(doc.createTextNode(it["title"]))
        item_el.appendChild(doc.createElement("link")).appendChild(doc.createTextNode(it["archive_link"]))
        item_el.appendChild(doc.createElement("guid")).appendChild(doc.createTextNode(it["orig_link"]))
        item_el.appendChild(doc.createElement("description")).appendChild(doc.createTextNode(it["summary"]))
        item_el.appendChild(doc.createElement("pubDate")).appendChild(
            doc.createTextNode(email.utils.format_datetime(it["published_dt"]))
        )

    with open(OUTPUT_FILE, "wb") as f:
        f.write(doc.toxml(encoding="utf-8"))

    print(f"✅ {OUTPUT_FILE} generated with {len(all_entries)} articles.")

if __name__ == "__main__":
    main()
