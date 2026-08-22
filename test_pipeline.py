#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from extract import extract_reel, cleanup_reel
from understand import process_reel_understanding
from bot import summarize
from notion_writer import post_to_notion

def run_test():
    test_url = "https://www.instagram.com/reel/DcWWtRwvYbQ"
    print(f"[test] Testing full pipeline for URL: {test_url}")
    
    # 1. Download & Extract
    print("[test] Step 1: extract_reel...")
    reel_dir = extract_reel(test_url)
    print(f"[test] Extracted to: {reel_dir}")
    
    # 2. Understand
    print("[test] Step 2: process_reel_understanding...")
    combined_path = process_reel_understanding(reel_dir)
    context_text = combined_path.read_text(encoding="utf-8")
    print(f"[test] Combined context length: {len(context_text)} chars")
    
    # 3. Summarize
    print("[test] Step 3: Ollama summarize...")
    sum_dict = summarize(context_text)
    print(f"[test] Summary result: {sum_dict}")
    
    # 4. Notion
    print("[test] Step 4: Notion post...")
    title = sum_dict.get("title", "Test Reel")
    summary = str(sum_dict.get("summary", ""))
    tags = sum_dict.get("tags", ["test"])
    notion_url = post_to_notion(title, summary, "", test_url, "2026-08-23", tags)
    print(f"[test] Notion URL: {notion_url}")
    
    # 5. Cleanup
    print("[test] Step 5: Cleanup...")
    cleanup_reel(reel_dir)
    print("[test] Pipeline test complete SUCCESS!")

if __name__ == "__main__":
    run_test()
