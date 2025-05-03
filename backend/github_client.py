"""
github-client.py

Handles GitHub API calls and direct patch/diff scraping for PRs.
"""

import requests
import os
from typing import Any, Dict, List, Optional

# Optionally set a GitHub token for authenticated requests (higher rate limits)
GITHUB_TOKEN: Optional[str] = os.environ.get('GITHUB_TOKEN')


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
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch repo metadata: {response.status_code} {response.text}")
    return response.json()


def list_merged_prs(owner: str, repo: str) -> List[Dict[str, Any]]:
    """
    List merged pull requests for a repository using the GitHub API.
    Args:
        owner: Repository owner username or org
        repo: Repository name
    Returns:
        List of dictionaries, each representing a merged PR
    """
    pass


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
    pass 

if __name__ == "__main__":
    owner = "facebook"
    repo = "react"
    try:
        metadata = fetch_repo_metadata(owner, repo)
        print("Repository metadata:")
        print(metadata)
    except Exception as e:
        print(f"Error: {e}") 