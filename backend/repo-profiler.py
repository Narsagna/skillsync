"""
repo-profiler.py

Script for extracting and synthesizing repository profile information from a GitHub repository's README.
"""

from dataclasses import dataclass
import argparse
import requests
import sys
import os
from github_client import GITHUB_TOKEN
from pydantic import BaseModel
from enum import Enum
from typing import Any, Dict
import json
import re

@dataclass
class Prompts:
    extraction_guidelines: str
    intermediate_type_definition: str
    synthesis_guidelines: str
    final_type_definition: str

readme_prompts = Prompts(
    extraction_guidelines="""
    Analyze this repository README to extract critical information about:
    1. The repository's purpose, main technologies, and core functionality
    2. Prerequisites and requirements for contributing to this project
    3. Key technical areas and skills that would be valuable for contributors
    
    Focus on technical details, programming languages, frameworks, architectural patterns, 
    and specific domain knowledge that would be relevant for understanding PRs in this repository.
    """,
    intermediate_type_definition="",  # Will remain empty as not needed
    synthesis_guidelines="""
    IMPORTANT: You must return ONLY a valid JSON object as your entire response - no introduction, explanation, or additional text.
    
    Based on the README analysis, create a concise repository profile that summarizes:
    1. A one-line description of what the repository is about
    2. The main technical stack and frameworks used
    3. Prerequisites for contributing (environment setup, knowledge requirements)
    4. Key technical areas and skills someone would need to contribute effectively
    
    This summary will be used to provide context when analyzing pull requests.
    Prioritize technical details that would help in evaluating a contributor's skills.
    
    Do not include any text before or after the JSON object. The response must begin with '{' and end with '}' with no additional characters.
    Ensure the JSON structure exactly matches the final type definition below.
    """,
    final_type_definition="""
    type RepositoryContext = {
        description: string;  // One-line description of the repository
        tech_stack: string[]; // Main technologies, languages, frameworks used
        contribution_prerequisites: {
            requirement: string;
            description: string;
        }[];
        key_skills: {
            skill: string;
            importance: "critical" | "high" | "medium" | "nice-to-have";
            context?: string;
        }[];
        domain_knowledge: string[]; // Specific domain expertise that would be valuable
    }
    """
)

LLAMA_API_URL = "https://api.llama.com/v1/chat/completions"
LLAMA_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY")

class Provider(str, Enum):
    llama = "llama"
    # Add other providers as needed

class ReadmeAnalysis(BaseModel):
    """
    Stores the results of README analysis, including provider, repository info, and analysis results.
    """
    provider: Provider = Provider.llama
    repository: str
    name: str
    analysis: Dict[Any, Any]

def fetch_readme(owner: str, repo: str) -> str:
    """
    Fetch the README file content for a given repository using the GitHub API.
    Returns the README content as a string.
    Raises an exception if not found.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch README: {response.status_code} {response.text}")
    return response.text

def analyze_readme_with_llama(readme_content: str, prompt: str) -> str:
    if not LLAMA_API_KEY:
        raise Exception("LLAMA_API_KEY environment variable not set.")
    payload = {
        "model": LLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt + "\n" + readme_content}
        ],
        "max_completion_tokens": 1024,
        "temperature": 0.7
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLAMA_API_KEY}"
    }
    response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=60)
    if response.status_code != 200:
        raise Exception(f"Llama API error: {response.status_code} {response.text}")
    result = response.json()
    # Extract the AI's reply from the response
    try:
        ai_message = result["completion_message"]["content"]["text"]
    except Exception:
        ai_message = result.get("response", str(result))
    return ai_message

def extract_owner_repo_from_url(repository_url: str):
    """
    Extracts the owner and repo name from a GitHub repository URL.
    Example: https://github.com/facebook/react -> ("facebook", "react")
    """
    pattern = r"github\.com[/:]([\w.-]+)/([\w.-]+)(?:\.git)?/?"
    match = re.search(pattern, repository_url)
    if not match:
        raise ValueError(f"Invalid GitHub repository URL: {repository_url}")
    return match.group(1), match.group(2)

def main():
    parser = argparse.ArgumentParser(description="Repository Profiler: Analyze a GitHub repo's README.")
    parser.add_argument("repository_url", help="GitHub repository URL (e.g. https://github.com/facebook/react)")
    args = parser.parse_args()

    try:
        owner, repo = extract_owner_repo_from_url(args.repository_url)
        readme_content = fetch_readme(owner, repo)
        prompt = readme_prompts.synthesis_guidelines + "\n" + readme_prompts.final_type_definition
        print("[INFO] Sending README to Llama for analysis...")
        profile_json = analyze_readme_with_llama(readme_content, prompt)
        try:
            analysis_dict = json.loads(profile_json)
        except json.JSONDecodeError:
            print("Llama response was not valid JSON:")
            print(profile_json)
            sys.exit(1)
        analysis_result = ReadmeAnalysis(
            provider=Provider.llama,
            repository=f"{owner}/{repo}",
            name=repo,
            analysis=analysis_dict
        )
        print(analysis_result.model_dump_json(indent=2))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Future: Add CLI and analysis logic here 