import os
import json
import re
from typing import Any, Dict
from pydantic import BaseModel
from db import Repository, PullRequest, SessionLocal, init_db
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

# Prompt definitions (copied from pr_profiler.py)
from pr_profiler import pr_prompts

PATCHES_PATH = 'all_patches.txt'
METADATA_PATH = 'pr_metadata.json'
LLAMA_API_URL = "https://api.llama.com/v1/chat/completions"
LLAMA_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY")

class PRAnalysis(BaseModel):
    repo_url: str
    pr_number: int
    developer: str
    title: str
    analysis: Dict[Any, Any]

def parse_patches(patches_path):
    pr_number = None
    diff_lines = []
    in_pr = False
    pr_start_re = re.compile(r'^===== PR #(\d+) =====$')
    pr_end_re = re.compile(r'^===== END PR #(\d+) =====$')
    with open(patches_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            start_match = pr_start_re.match(line.strip())
            end_match = pr_end_re.match(line.strip())
            if start_match:
                pr_number = start_match.group(1)
                diff_lines = []
                in_pr = True
            elif end_match and in_pr and end_match.group(1) == pr_number:
                yield pr_number, ''.join(diff_lines)
                pr_number = None
                diff_lines = []
                in_pr = False
            elif in_pr:
                diff_lines.append(line)

def load_metadata(metadata_path):
    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata_list = json.load(f)
    return {str(item['pr_number']): item for item in metadata_list}

def analyze_local_pr(repo_url, pr_number, meta, diff):
    # Prepare prompt for Llama
    llama_prompt = pr_prompts.synthesis_guidelines + "\n" + pr_prompts.final_type_definition
    pr_info_str = f"PR Title: {meta.get('title', '')}\nAuthor: {meta.get('author', '')}\n"
    diff_str = f"Diff:\n{diff[:5000]}\n"  # Truncate if too large
    # No review messages for local
    full_prompt = llama_prompt + pr_info_str + diff_str

    if not LLAMA_API_KEY:
        raise Exception("LLAMA_API_KEY environment variable not set.")
    payload = {
        "model": LLAMA_MODEL,
        "messages": [
            {"role": "user", "content": full_prompt}
        ],
        "max_completion_tokens": 2048,
        "temperature": 0.7
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLAMA_API_KEY}"
    }
    import requests
    response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=90)
    if response.status_code != 200:
        raise Exception(f"Llama API error: {response.status_code} {response.text}")
    result = response.json()
    try:
        text_response = result["completion_message"]["content"]["text"]
        # Clean the response: Remove markdown code block markers if present
        cleaned_text = text_response
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json", 1)[1]
        if "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```", 1)[0]
        cleaned_text = cleaned_text.strip()
        analysis_result_dict = json.loads(cleaned_text)
    except Exception as e:
        print(f"[ERROR] Failed to parse Llama response: {e}")
        print(f"[ERROR] Raw response content: {result}")
        raise Exception(f"Failed to parse Llama response: {str(e)}. Raw response: {result}")
    return PRAnalysis(
        repo_url=repo_url,
        pr_number=int(pr_number),
        developer=meta.get("author", "Unknown"),
        title=meta.get("title", ""),
        analysis={
            "ai_analysis": analysis_result_dict,
            "direct_metadata": meta
        }
    )

def pydantic_to_db_pr(pydantic_obj: PRAnalysis) -> PullRequest:
    return PullRequest(
        repo_url=pydantic_obj.repo_url,
        pr_number=pydantic_obj.pr_number,
        developer=pydantic_obj.developer,
        title=pydantic_obj.title,
        details=pydantic_obj.analysis
    )

def analyze_and_store_local_pr(repo_url, pr_number, meta, diff):
    session = SessionLocal()
    try:
        pr_row = session.query(PullRequest).filter_by(repo_url=repo_url, pr_number=int(pr_number)).first()
        if pr_row:
            print(f"[INFO] PR #{pr_number} already analyzed. Skipping.")
            return
        result = analyze_local_pr(repo_url, pr_number, meta, diff)
        db_obj = pydantic_to_db_pr(result)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        print(f"[INFO] Analysis for PR #{pr_number} stored in database.")
    except Exception as e:
        print(f"[ERROR] Failed to analyze PR #{pr_number}: {e}")
    finally:
        session.close()

def is_pr_in_db(pr_number, repo_url):
    from db import SessionLocal, PullRequest
    db = SessionLocal()
    try:
        return db.query(PullRequest).filter_by(repo_url=repo_url, pr_number=pr_number).first() is not None
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze local PR patches and index them in the DB.")
    parser.add_argument("repo_url", type=str, help="Repository URL (e.g. owner/repo)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PRs to process")
    args = parser.parse_args()

    repo_url = args.repo_url
    limit = args.limit

    # Load all patches and metadata
    patches = list(parse_patches(PATCHES_PATH))
    metadata = load_metadata(METADATA_PATH)

    indexed = []
    skipped = []
    failed = []
    count = 0
    for pr_number, patch in patches:
        if limit and count >= limit:
            break
        if is_pr_in_db(pr_number, repo_url):
            print(f"[SKIP] PR {pr_number} already indexed.")
            skipped.append(pr_number)
            continue
        try:
            # You may need to adapt this to your actual analysis/indexing logic
            analyze_and_store_local_pr(repo_url, pr_number, metadata.get(str(pr_number), {}), patch)
            print(f"[INDEXED] PR {pr_number} indexed successfully.")
            indexed.append(pr_number)
        except Exception as e:
            print(f"[FAIL] PR {pr_number} failed to index: {e}")
            failed.append((pr_number, str(e)))
        count += 1

    print("\n==== SUMMARY ====")
    print(f"Indexed: {len(indexed)} PRs")
    print(f"Skipped: {len(skipped)} PRs (already in DB)")
    print(f"Failed: {len(failed)} PRs")
    if failed:
        print("Failed PRs:")
        for pr_number, err in failed:
            print(f"  PR {pr_number}: {err}")