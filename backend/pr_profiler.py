"""
pr_profiler.py

Script for extracting and synthesizing pull request analysis from a GitHub repository.
"""

from dataclasses import dataclass
from pydantic import BaseModel
from typing import Any, Dict, List
import requests
import os
import json
from github_client import fetch_comprehensive_pr_metadata, list_merged_prs
from db import Repository, PullRequest, SessionLocal
from datetime import datetime, timedelta, timezone
import argparse
from db import init_db
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class Prompts:
    extraction_guidelines: str
    intermediate_type_definition: str
    synthesis_guidelines: str
    final_type_definition: str

pr_prompts = Prompts(
    extraction_guidelines="""
    You are an AI assistant helping developers and engineering managers summarize and classify GitHub or Bitbucket pull requests. These summaries would later be used to identify the skills exhibited by the developer.

    Your first job is to extract key details from the PR. Read the title, description, and code diff provided to you, and identify:

    1. What was changed? Summarize the core logic or modification made.
    2. Where was it changed? Mention relevant modules, files, or layers.
    3. Why was it changed? (If possible, infer the reason from description or code.)
    4. How was it changed? Note the approach taken and any patterns in implementation.
    5. How many lines of code were added or removed and what was the language?

    Focus on what functionality was introduced, modified, or removed. You don't need to restate every line of code. Summarize the intent and focus of the change.

    In addition to the code diff, develop your understanding from:
    - File paths and filenames
    - Function or class names added/modified
    - Comments or logs in the code
    - Description or commit messages
    - Discussion threads and review comments
    - Change iterations and how the PR evolved

    Make sure to note what skills were exhibited by the developer in this PR. Classify them under the following categories:
    
    - `tech_stack`: Languages, frameworks, libraries, tools used in the implementation
    
    - `domain_expertise`: Identify the developer's understanding of specific business or product domains demonstrated in their contributions. Be specific about the sub-domain. This could be (but not limited to) the following:

      1. Classic Business Domain examples:
         - Financial systems (payments, billing, accounting)
         - Customer management (identity, user management)
         - Ecommerce (catalog, inventory, checkout, fulfillment)
         - Content systems (CMS, knowledge bases, media management)
         - Analytics (tracking, reporting, insights)
         - Operations (supply chain, manufacturing, logistics)
         - Marketing (campaigns, A/B testing, personalization)
      
      2. Product-as-Domain examples: For technical products where the product IS the domain:
         - Developer Tools: Expertise in specific IDE features, compilation systems, debugging tools
         - Data Systems: Knowledge of query optimization, storage engines, replication
         - Infrastructure: Understanding of deployment systems, container orchestration, networking
         - Security: Authentication mechanisms, vulnerability assessment, encryption systems
      
      Look for signals such as:
      - Domain-specific terminology used correctly in comments and commit messages
      - Awareness of business logic edge cases specific to that domain
      - Reference to domain-specific standards or best practices
      - Proper handling of domain-specific validation or processing rules
      - Intelligent trade-offs that show understanding of domain priorities
    
    - `architectural_and_systems_thinking`: Ability to understand and improve the structure, scalability, and long-term maintainability of systems. Look for evidence of:

      1. Design Patterns and Abstractions:
         - Creating or improving abstractions that simplify complex logic
         - Applying appropriate design patterns to solve problems
         - Establishing clear separation of concerns
         - Creating flexible interfaces that hide implementation details
    
      2. System-Level Considerations:
         - Performance optimizations with system-wide impact
         - Addressing scalability constraints or bottlenecks
         - Improving error handling and resilience across components
         - Considering security implications across the system
         - Identifying and improving critical paths in the system to enhance reliability
         - Understanding dependencies between components and managing their interactions
    
      3. Technical Debt Management:
         - Refactoring code to improve maintainability
         - Cleaning up inconsistent patterns or approaches
         - Consolidating duplicate functionality
         - Improving code organization and structure
    
      4. Future-Proofing:
         - Making changes extensible for anticipated future requirements
         - Adding appropriate configuration options or feature flags
         - Ensuring backward compatibility where needed
         - Documenting architectural decisions and rationales
    
      Look for signals such as:
      - Comments explaining architectural decisions or trade-offs
      - PRs that reorganize code without changing functionality
      - Introduction of abstraction layers or interfaces
      - Discussions about system-wide implications of changes
      - Efficiency improvements that consider the broader system context
    
    - `behavioral_signals`: For each PR, collect evidence that indicates the developer's work style along two axes, which will later help categorize them into one of the four archetypes:

      1. X-Axis: Execution-Oriented vs. Exploration-Oriented
         
         Execution-Oriented signals (look for evidence of):
         - Task completion efficiency and speed
         - Implementation of established solutions
         - Practical, direct approaches to problems
         - Focus on shipping working code
         - Linear, methodical implementation processes
         - Results-oriented comments and descriptions
         
         Exploration-Oriented signals (look for evidence of):
         - Trying multiple approaches or techniques
         - Introducing new libraries or patterns
         - Questioning existing solutions or patterns
         - Research references or experimental aspects
         - Iterations that show evolution of thinking
      
      2. Y-Axis: Broad Scope vs. Specialized Scope
         
         Broad Scope signals (look for evidence of):
         - Changes spanning multiple components or modules
         - Versatility across different areas of the system
         - Addressing cross-cutting concerns
         - Working at different layers of the stack
         - System-level awareness in comments or approach
         
         Specialized Scope signals (look for evidence of):
         - Deep focus within specific modules
         - Expert-level knowledge in particular areas
         - Detailed optimizations or improvements
         - Craftsmanship and attention to specific details
         - Consistent focus on the same areas over time

      For each PR, collect concrete examples of behaviors from each category. For example:
      - "Implemented solution using established patterns in the codebase" (Execution-Oriented)
      - "Examined three different approaches before selecting final implementation" (Exploration-Oriented)
      - "Made changes across authentication, payment, and notification systems" (Broad Scope)
      - "Deep optimization of database query patterns with specialized knowledge" (Specialized Scope)
      
      The objective is to collect specific evidence from multiple PRs to later place the developer in one of the four quadrants:
      - High-Output Executor (Execution-Oriented + Broad Scope)
      - Domain Specialist/Quality Guardian (Execution-Oriented + Specialized Scope)
      - Polymath Generalist (Exploration-Oriented + Broad Scope)
      - Innovator/Architect (Exploration-Oriented + Specialized Scope)

    For behavioral signals, draw evidence from:
    - PR discussion threads
    - Number and nature of iterations
    - Self-identified vs reviewer-identified issues
    - Documentation and test coverage changes
    - Quality and detail of commit messages
    - Size and scope management of the PR
    - Responsiveness to feedback
    - Patterns across multiple PRs when available

    /* Make the insights as concise as possible, focusing on the most relevant information. */
    """,
    intermediate_type_definition="",
    synthesis_guidelines="""
    IMPORTANT: You must return ONLY a valid JSON object as your entire response - no introduction, explanation, or additional text.
    
    Based on the extracted information, do the following:

    1. Classify the Pull Request using the [Conventional Commit types]:
    - `feat`: A new feature
    - `fix`: A bug fix
    - `build`: Changes to build system or external dependencies
    - `chore`: Maintenance tasks not related to features or tests
    - `ci`: CI/CD pipeline or config changes
    - `docs`: Documentation-only changes
    - `style`: Code formatting, linting, or styling
    - `refactor`: Code restructuring without feature or bug change
    - `perf`: Performance improvements
    - `test`: Changes or additions to tests

    2. Tag the PR as one of the following based on its context:**
    - `domain`: Changes to business logic (e.g., payment routing, onboarding)
    - `framework`: Changes to shared utilities, libraries, platform code, infrastructure
    - `others`: Docs, formatting, build scripts, minor changes without clear domain relevance

    Provide a short justification for both classifications. Avoid just restating filenames; explain your reasoning briefly.

    If you're unsure, guess based on the best available signals.

    Here's an example:
    
    Example 1: Feature (feat) / Domain Logic
    Title: feat(decision): add support to register API keys to proxy  
    Description: This PR adds support for registering API keys from the decision layer to enable key-based authorization in downstream services. The implementation includes a new caching mechanism to improve performance on the critical path.
    
    Diff Summary:
    - Added API in `decision.rs` with new endpoint for key registration
    - Created abstraction layer in `api_keys.rs` to handle different storage backends
    - Implemented caching strategy to minimize latency on auth checks
    - Added comprehensive error handling for network failures
    - Modified metrics to log key registrations and cache performance
    
    Output:
    {
        "summary": "Adds a new feature to register and store API keys via the decision layer with an efficient caching mechanism for downstream authorization.",
        "pr_type": "feat",
        "pr_reason": "Introduces a new capability (API key registration) with performance optimizations on a critical path.",
        "domain_tag": "domain",
        "tag_reason": "Changes affect the decision layer and API key logic, which are core to the business logic of the authorization system.",
        "skills": [
            {
                "name": "Rust",
                "category": "tech_stack",
                "frequency": 250,
                "unit": "lines",
                "evidence": "Implementation in Rust throughout decision.rs and api_keys.rs files"
            },
            {
                "name": "Authentication Systems",
                "category": "domain_expertise", 
                "frequency": 1,
                "unit": "feature",
                "evidence": "Demonstrated understanding of API key-based authentication concepts and best practices, including secure storage considerations and downstream service integration"
            },
            {
                "name": "API Development",
                "category": "domain_expertise",
                "evidence": "Changes to multiple API endpoints and handlers to enable filtering and improved error reporting.",
                "frequency": 2,
                "unit": "endpoints"
            },
            {
                "name": "Cache Strategy Design",
                "category": "architectural_and_systems_thinking",
                "frequency": 1,
                "unit": "component",
                "evidence": "Created an efficient caching mechanism that minimizes latency on the critical authorization path, showing awareness of system reliability requirements"
            },
            {
                "name": "Abstraction Design",
                "category": "architectural_and_systems_thinking",
                "frequency": 1,
                "unit": "component",
                "evidence": "Implemented a storage abstraction layer in api_keys.rs to allow for different backends, demonstrating good separation of concerns"
            },
            {
                "name": "System-Wide Error Handling",
                "category": "architectural_and_systems_thinking",
                "frequency": 3,
                "unit": "modules",
                "evidence": "Added comprehensive error handling for network failures, showing consideration for system reliability"
            },
            {
                "name": "Task Execution Focus",
                "category": "behavioral_signals",
                "frequency": 1,
                "unit": "implementation",
                "evidence": "Direct implementation of the required feature with practical design choices",
                "execution_exploration": {
                    "tendency": "strongly_execution",
                    "evidence": "Focused on implementing a solution efficiently using established patterns within the codebase"
                },
                "scope_breadth": {
                    "tendency": "moderately_specialized",
                    "evidence": "Concentrated on the authorization domain but included considerations across multiple components (API, storage, caching, metrics)"
                }
            }
        ]
    }

    Now, based on the input below, generate the output in the same format.

    Do not include any text before or after the JSON object. The response must begin with '{' and end with '}' with no additional characters.
    Ensure the JSON structure exactly matches the final type definition below.
    """,
    
    final_type_definition="""
    type FinalType = {
        work: {
            "summary": "<1 or 2 sentence summary of what this PR does>",
            "pr_type": "<one of: feat | fix | build | chore | ci | docs | style | refactor | perf | test>",
            "pr_reason": "<short justification of the objective and what the PR achieves>",
            "domain_tag": "<one of: domain | framework | others>",
            "tag_reason": "<short justification>",
            "skills": Skill[]
        }
        metadata: {
            "code_changes": {
                "lines_of_code": number;
                "language": string;
            }[]
        }
    }
    type Skill = {
        name: string; // one skill at a time, be specific (skill name cannot be the same as the category name)
        category: "tech_stack" | "domain_expertise" | "architectural_and_systems_thinking" | "behavioral_signals";
        frequency: number; // Appropriate metric based on category
        
        // Unit of measurement appropriate to the skill category
        // The unit should reflect what's being measured in a single PR:
        // 
        // For tech_stack:
        // - "lines" - Always use lines of code in the case of a language
        // - "files" - number of files using the technology
        // - "modules" - number of modules or components using the technology
        // - "functions" - number of functions of the framework used
        //
        // For domain_expertise:
        // - "features" - a domain-specific feature implemented
        // - "components" - a domain-specific component modified
        // - "domain_concepts" - application of a specific domain concept
        // - "implementations" - implementation of domain-specific logic
        //
        // For architectural_and_systems_thinking:
        // - "components" - architectural component designed or modified
        // - "patterns" - design pattern implemented
        // - "abstractions" - abstraction created or improved
        // - "system_enhancements" - system-level improvement
        // - "modules" - number of modules affected by architectural change
        //
        // For behavioral_signals:
        // - "implementations" - approach to implementation
        // - "iterations" - iterative refinement in the PR
        // - "comments" - behavioral evidence in comments or discussion
        // - "decisions" - decision-making pattern exhibited
        unit: string;
        
        evidence: string; // Textual explanation with examples or code snippets that demonstrate the skill
        
        // For behavioral signals specifically for the 2x2 matrix:
        execution_exploration?: {
            tendency: "strongly_execution" | "moderately_execution" | "balanced" | "moderately_exploration" | "strongly_exploration";
            evidence: string; // Specific examples from PR that support this classification
        };
        
        scope_breadth?: {
            tendency: "highly_specialized" | "moderately_specialized" | "balanced" | "moderately_broad" | "very_broad";
            evidence: string; // Specific examples from PR that support this classification
        };
    };
    """
)

class PRAnalysis(BaseModel):
    """
    Stores the results of PR analysis, including repo, PR number, developer, and analysis results.
    """
    repo_url: str
    pr_number: int
    developer: str
    title: str
    analysis: Dict[Any, Any]

LLAMA_API_URL = "https://api.llama.com/v1/chat/completions"
LLAMA_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY")

def analyze_pr(owner: str, repo: str, pr_number: int) -> PRAnalysis:
    """
    Analyze a pull request: fetch repo context, PR metadata, check merge, fetch conversation, run AI analysis, and store result.
    """
    # Fetch repository context (assume from db for now)
    db = SessionLocal()
    repo_url = f"{owner}/{repo}"
    repo_obj = db.query(Repository).filter_by(repo_url=repo_url).first()
    repo_context = repo_obj.details if repo_obj else None

    # Fetch PR metadata
    pr_metadata = fetch_comprehensive_pr_metadata(owner, repo, pr_number)

    # Check if PR is merged
    if not pr_metadata.get("merged_at"):
        db.close()
        raise Exception(f"PR #{pr_number} is not merged.")

    # Fetch PR conversation (already included in pr_metadata: title, author, review_messages)
    # Remove heavy data before storing
    metadata_to_store = dict(pr_metadata)
    metadata_to_store.pop("diff_data", None)
    metadata_to_store.pop("review_messages", None)

    # Prepare prompt for Llama (combine repo context, PR metadata, diff, review messages)
    llama_prompt = pr_prompts.synthesis_guidelines + "\n" + pr_prompts.final_type_definition
    context_str = f"Repository Context:\n{json.dumps(repo_context, indent=2)}\n" if repo_context else ""
    pr_info_str = f"PR Title: {pr_metadata.get('title', '')}\nAuthor: {pr_metadata.get('author', '')}\n"
    diff_str = f"Diff:\n{pr_metadata.get('diff_data', '')[:5000]}\n"  # Truncate if too large
    reviews_str = f"Review Comments:\n{json.dumps(pr_metadata.get('review_messages', []), indent=2)[:3000]}\n"
    full_prompt = llama_prompt + context_str + pr_info_str + diff_str + reviews_str

    # Call Llama API
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
    response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=90)
    if response.status_code != 200:
        db.close()
        raise Exception(f"Llama API error: {response.status_code} {response.text}")
    result = response.json()
    # Extract the AI's reply from the response
    try:
        ai_message = result["completion_message"]["content"]["text"]
        analysis_result_dict = json.loads(ai_message)
    except Exception:
        db.close()
        raise Exception(f"Llama response was not valid JSON: {result}")

    db.close()
    return PRAnalysis(
        repo_url=repo_url,
        pr_number=pr_number,
        developer=pr_metadata.get("author", "Unknown"),
        title=pr_metadata.get("title", ""),
        analysis={
            "ai_analysis": analysis_result_dict,
            "direct_metadata": metadata_to_store
        }
    )

def pydantic_from_db_pr(db_obj: PullRequest) -> PRAnalysis:
    """
    Convert a PullRequest database object to a PRAnalysis Pydantic model.
    """
    return PRAnalysis(
        repo_url=db_obj.repo_url,
        pr_number=db_obj.pr_number,
        developer=db_obj.developer,
        title=db_obj.title,
        analysis=db_obj.details
    )

def pydantic_to_db_pr(pydantic_obj: PRAnalysis) -> PullRequest:
    """
    Convert a PRAnalysis Pydantic model to a PullRequest database object (not committed).
    """
    return PullRequest(
        repo_url=pydantic_obj.repo_url,
        pr_number=pydantic_obj.pr_number,
        developer=pydantic_obj.developer,
        title=pydantic_obj.title,
        details=pydantic_obj.analysis
    )

def parse_time_period(period: str) -> datetime:
    """Parse time period strings like '30d', '6m', '1y' and return the corresponding date."""
    import re
    from dateutil.relativedelta import relativedelta
    if not period:
        return datetime.utcnow() - timedelta(days=30)
    match = re.match(r'^(\d+)([dmy])$', period.lower())
    if not match:
        raise ValueError(f"Invalid time period format: {period}. Use format like '30d', '6m', '1y'")
    value, unit = match.groups()
    value = int(value)
    now = datetime.now(timezone.utc)
    if unit == 'd':
        return now - timedelta(days=value)
    elif unit == 'm':
        return now - relativedelta(months=value)
    elif unit == 'y':
        return now - relativedelta(years=value)
    else:
        raise ValueError(f"Unknown time unit: {unit}")

def analyze_and_store_pr(owner, repo, pr_number):
    from db import SessionLocal, PullRequest
    session = SessionLocal()
    repo_url = f"{owner}/{repo}"
    try:
        pr_row = session.query(PullRequest).filter_by(repo_url=repo_url, pr_number=pr_number).first()
        if pr_row:
            print(f"[INFO] PR #{pr_number} already analyzed. Skipping.")
            return
        result = analyze_pr(owner, repo, pr_number)
        db_obj = pydantic_to_db_pr(result)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        print(f"[INFO] Analysis for PR #{pr_number} stored in database.")
    except Exception as e:
        print(f"[ERROR] Failed to analyze PR #{pr_number}: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch analyze merged PRs in a repo.")
    parser.add_argument("repo", type=str, help='Repository in the format "owner/repo"')
    parser.add_argument("--author", type=str, help="Optional: Author name to filter PRs by")
    parser.add_argument("--period", type=str, default="30d", help='Time period to look back (e.g., "30d", "6m", "1y")')
    parser.add_argument("--parallel", type=int, default=2, help="Number of PRs to analyze in parallel (default: 2)")
    parser.add_argument("--limit", type=int, default=10, help="Limit the number of PRs to analyze (default: 10)")
    args = parser.parse_args()

    owner, repo = args.repo.split("/")
    period = args.period
    author = args.author
    max_workers = args.parallel

    # Ensure DB tables are created
    init_db()

    since_date = parse_time_period(period)
    db = SessionLocal()
    try:
        merged_prs = list_merged_prs(owner, repo, limit=args.limit) or []
        print(f"[INFO] Found {len(merged_prs)} merged PRs in repo {owner}/{repo}")

        pr_numbers_to_analyze = []
        for pr in merged_prs:
            merged_at_str = pr.get("merged_at")
            if not merged_at_str:
                continue
            merged_at = datetime.strptime(merged_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if merged_at < since_date:
                continue
            if author and pr.get("user", {}).get("login") != author:
                continue
            pr_number = pr.get("number")
            pr_row = db.query(PullRequest).filter_by(repo_url=f"{owner}/{repo}", pr_number=pr_number).first()
            if not pr_row:
                pr_numbers_to_analyze.append(pr_number)
            else:
                print(f"[INFO] PR #{pr_number} already analyzed. Skipping.")

        print(f"[INFO] {len(pr_numbers_to_analyze)} PRs to analyze in parallel.")

        pr_numbers_to_analyze = pr_numbers_to_analyze[:args.limit]

        # Parallel analysis
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(analyze_and_store_pr, owner, repo, pr_number)
                for pr_number in pr_numbers_to_analyze
            ]
            for future in as_completed(futures):
                future.result()

    finally:
        db.close() 