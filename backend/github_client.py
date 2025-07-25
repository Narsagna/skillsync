"""
github-client.py

Handles GitHub API calls and direct patch/diff scraping for PRs.
"""

import requests
import os
from typing import Any, Dict, List, Optional
from datetime import datetime
import itertools

# Load tokens from file
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'github_tokens.txt')
with open(TOKEN_FILE, 'r') as f:
    TOKENS = [line.strip() for line in f if line.strip()]
if not TOKENS:
    raise Exception("No GitHub tokens found in backend/github_tokens.txt")
token_cycle = itertools.cycle(TOKENS)

def get_next_token():
    token = next(token_cycle)
    print(f"[TOKEN] Using token: {token[:8]}...")  # Only print the first 8 chars for security
    return token

def fetch_repo_metadata(owner: str, repo: str) -> Dict[str, Any]:
    """
    Fetch repository metadata from the GitHub API.
    Args:
        owner: Repository owner username or org
        repo: Repository name
    Returns:
        Dictionary with repository metadata
    Raises:
        Exception if the request fails
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    token = get_next_token()
    headers = {"Authorization": f"token {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch repo metadata: {response.status_code} {response.text}")
    return response.json()


def list_merged_prs(owner: str, repo: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List merged pull requests for a repository using the GitHub API.
    Args:
        owner: Repository owner username or org
        repo: Repository name
        limit: Maximum number of merged PRs to return (optional)
    Returns:
        List of dictionaries, each representing a merged PR
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    token = get_next_token()
    headers = {"Authorization": f"token {token}"}
    params = {"state": "closed", "per_page": 100}
    prs = []
    page = 1
    while True:
        params["page"] = page
        print(f"[GITHUB] Fetching PRs page {page}...")
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"[ERROR] Failed to fetch PRs: {response.status_code} {response.text}")
            print(f"[ERROR] Response headers: {response.headers}")
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
                print(f"[RATE LIMIT] X-RateLimit-Remaining: {response.headers.get('X-RateLimit-Remaining')}")
                print(f"[RATE LIMIT] X-RateLimit-Reset: {response.headers.get('X-RateLimit-Reset')}")
            raise Exception(f"Failed to fetch PRs: {response.status_code} {response.text}")
        data = response.json()
        print(f"[GITHUB] Page {page}: fetched {len(data)} PRs.")
        if not data:
            break
        for pr in data:
            if pr.get("merged_at"):
                prs.append(pr)
                if limit is not None and len(prs) >= limit:
                    print(f"[GITHUB] Reached limit of {limit} merged PRs.")
                    return prs
        print(f"[GITHUB] Total merged PRs collected so far: {len(prs)}")
        page += 1
    print(f"[GITHUB] Finished fetching merged PRs. Total: {len(prs)}")
    return prs  # Always return a list


def fetch_pr_patch(owner: str, repo: str, pr_number: int) -> str:
    """
    Fetch the .patch content for a pull request using the direct URL.
    Args:
        owner: Repository owner username or org
        repo: Repository name
        pr_number: Pull request number
    Returns:
        String containing the patch content
    """
    url = f"https://github.com/{owner}/{repo}/pull/{pr_number}.patch"
    token = get_next_token()
    headers = {"Authorization": f"token {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch PR patch: {response.status_code} {response.text}")
    return response.text


def fetch_pr_patch_and_comments(owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
    """
    Fetch the .patch content and review comments for a pull request.
    Returns a dictionary with 'patch' and 'review_comments'.
    """
    # Fetch patch
    patch_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}.patch"
    token = get_next_token()
    headers = {"Authorization": f"token {token}"}

    patch_response = requests.get(patch_url, headers=headers)
    if patch_response.status_code != 200:
        raise Exception(f"Failed to fetch PR patch: {patch_response.status_code} {patch_response.text}")

    # Fetch review comments
    review_comments_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
    token = get_next_token()
    headers["Authorization"] = f"token {token}"
    review_comments_response = requests.get(review_comments_url, headers=headers)
    if review_comments_response.status_code != 200:
        raise Exception(f"Failed to fetch PR review comments: {review_comments_response.status_code} {review_comments_response.text}")

    return {
        "patch": patch_response.text,
        "review_comments": review_comments_response.json()
    }


def fetch_comprehensive_pr_metadata(owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
    """
    Fetch comprehensive metadata for a pull request, including commits, reviews, diff, and stats.
    """
    token = get_next_token()
    headers = {"Authorization": f"token {token}"}

    # Fetch PR data
    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    pr_response = requests.get(pr_url, headers=headers)
    if pr_response.status_code != 200:
        raise Exception(f"Failed to fetch PR data: {pr_response.status_code} {pr_response.text}")
    pr_data = pr_response.json()

    # Fetch commits data
    commits_url = pr_data.get("commits_url")
    token = get_next_token()
    headers["Authorization"] = f"token {token}"
    commits_response = requests.get(commits_url, headers=headers)
    if commits_response.status_code != 200:
        raise Exception(f"Failed to fetch PR commits: {commits_response.status_code} {commits_response.text}")
    commits_data = commits_response.json()

    # Fetch reviews data
    reviews_url = pr_data.get("url") + "/reviews"
    token = get_next_token()
    headers["Authorization"] = f"token {token}"
    reviews_response = requests.get(reviews_url, headers=headers)
    if reviews_response.status_code != 200:
        raise Exception(f"Failed to fetch PR reviews: {reviews_response.status_code} {reviews_response.text}")
    reviews_data = reviews_response.json()

    # Fetch diff
    diff_url = f"https://github.com/{owner}/{repo}/pull/{pr_number}.diff"
    token = get_next_token()
    headers["Authorization"] = f"token {token}"
    diff_response = requests.get(diff_url, headers=headers)
    if diff_response.status_code != 200:
        raise Exception(f"Failed to fetch PR diff: {diff_response.status_code} {diff_response.text}")
    diff = diff_response.text

    # Calculate time to first review and time to merge
    created_at = pr_data.get("created_at")
    merged_at = pr_data.get("merged_at")
    first_review_time = None
    if reviews_data:
        review_times = [r.get("submitted_at") for r in reviews_data if r.get("submitted_at")]
        if review_times:
            first_review_time = min(review_times)
    def parse_time(t): return datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") if t else None
    time_to_review = (parse_time(first_review_time) - parse_time(created_at)).total_seconds() / 3600 if first_review_time and created_at else None
    time_to_merge = (parse_time(merged_at) - parse_time(created_at)).total_seconds() / 3600 if merged_at and created_at else None

    additions = pr_data.get("additions", 0)
    deletions = pr_data.get("deletions", 0)

    metadata = {
        "repo": repo,
        "pr_number": pr_number,
        "title": pr_data.get("title", ""),
        "author": pr_data.get("user", {}).get("login", "Unknown"),
        "created_at": created_at,
        "merged_at": merged_at,
        "time_to_first_review": time_to_review,
        "time_to_merge": time_to_merge,
        "additions": additions,
        "deletions": deletions,
        "pr_size": additions + deletions,
        "number_of_commits": pr_data.get("commits", 0),
        "commit": [
            {
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message", ""),
                "author": commit.get("commit", {}).get("author", {}).get("name", ""),
                "timestamp": commit.get("commit", {}).get("author", {}).get("date", "")
            }
            for commit in commits_data
        ],
        "review_messages": [
            {
                "reviewer": review.get("user", {}).get("login", "Unknown"),
                "state": review.get("state", ""),
                "body": review.get("body", ""),
                "submitted_at": review.get("submitted_at", "")
            }
            for review in reviews_data if review.get("body")
        ],
        "review_count": len(reviews_data),
        "diff_data": diff
    }
    return metadata


if __name__ == "__main__":
    owner = "facebook"
    repo = "react"
    try:
        metadata = fetch_repo_metadata(owner, repo)
        print("Repository metadata:")
        print(metadata)
    except Exception as e:
        print(f"Error: {e}") 