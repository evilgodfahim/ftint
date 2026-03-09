#!/usr/bin/env python3
import feedparser
from xml.dom.minidom import Document
import email.utils
from datetime import datetime, timezone

RSS_URLS = [
    "https://www.ft.com/rss/world"
]

ARCHIVE_PREFIX = "https://archive.is/o/wjemQ/"
OUTPUT_FILE = "combined.xml"

def parse_entry_datetime(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        from time import mktime
        ts = mktime(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        from time import mktime
        ts = mktime(entry.updated_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)

doc = Document()
rss = doc.createElement("rss")
rss.setAttribute("version", "2.0")
doc.appendChild(rss)

channel = doc.createElement("channel")
rss.appendChild(channel)
channel.appendChild(doc.createElement("title")).appendChild(doc.createTextNode("Project Syndicate Archive Feed"))
channel.appendChild(doc.createElement("link")).appendChild(doc.createTextNode("https://www.project-syndicate.org/"))
channel.appendChild(doc.createElement("description")).appendChild(doc.createTextNode("Combined feed with archive links"))

all_entries = []

for feed_url in RSS_URLS:
    feed = feedparser.parse(feed_url)
    for entry in feed.entries:
        dt = parse_entry_datetime(entry)
        all_entries.append({
            "title": getattr(entry, "title", "Untitled"),
            "orig_link": entry.link,
            "archive_link": ARCHIVE_PREFIX + entry.link,
            "summary": getattr(entry, "summary", "") or getattr(entry, "description", ""),
            "published_dt": dt
        })

# sort newest first
all_entries.sort(key=lambda x: x["published_dt"], reverse=True)

for it in all_entries:
    item_el = doc.createElement("item")
    channel.appendChild(item_el)
    item_el.appendChild(doc.createElement("title")).appendChild(doc.createTextNode(it["title"]))
    item_el.appendChild(doc.createElement("link")).appendChild(doc.createTextNode(it["archive_link"]))
    item_el.appendChild(doc.createElement("guid")).appendChild(doc.createTextNode(it["orig_link"]))
    item_el.appendChild(doc.createElement("description")).appendChild(doc.createTextNode(it["summary"]))
    pubdate = email.utils.format_datetime(it["published_dt"])
    item_el.appendChild(doc.createElement("pubDate")).appendChild(doc.createTextNode(pubdate))

# write to file
with open(OUTPUT_FILE, "wb") as f:
    f.write(doc.toxml(encoding="utf-8"))

print(f"✅ combined.xml generated with {len(all_entries)} articles.")
