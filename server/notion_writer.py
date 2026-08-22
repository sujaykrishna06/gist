#!/usr/bin/env python3
"""
Notion Integration Module for Gist
----------------------------------
Posts structured Reel summaries to a user's Notion database via Notion REST API.
Properties created:
  - Title (title)
  - Summary (rich_text)
  - Caption (rich_text)
  - Link (url)
  - Date (date)
  - Tags (multi_select)
Fails gracefully without crashing if credentials are absent or API returns error.
"""

import os
import json
import urllib.request
from typing import Optional, List

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"

def post_to_notion(
    title: str,
    summary: str,
    caption: str,
    link: str,
    date_str: str,
    tags: List[str]
) -> Optional[str]:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip()

    if not token or not db_id:
        print("[warn] NOTION_TOKEN or NOTION_DATABASE_ID not configured. Skipping Notion log.", flush=True)
        return None

    # Sanitize inputs for Notion payload limits
    clean_title = (title or "Untitled Reel Summary")[:2000]
    clean_summary = (summary or "")[:2000]
    clean_caption = (caption or "")[:2000]
    clean_tags = [{"name": str(t).replace(",", "")[:100]} for t in (tags or []) if str(t).strip()][:10]

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Title": {
                "title": [{"text": {"content": clean_title}}]
            },
            "Summary": {
                "rich_text": [{"text": {"content": clean_summary}}]
            },
            "Caption": {
                "rich_text": [{"text": {"content": clean_caption}}]
            },
            "Link": {
                "url": link
            },
            "Date": {
                "date": {"start": date_str}
            },
            "Tags": {
                "multi_select": clean_tags
            }
        }
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(NOTION_API_URL, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            notion_page_url = res_json.get("url")
            print(f"[notion] Successfully created Notion page: {notion_page_url}", flush=True)
            return notion_page_url
    except Exception as e:
        print(f"[warn] Failed to create Notion page: {e}", flush=True)
        return None
