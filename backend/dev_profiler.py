import json
from typing import Any, Dict, List
from db import SessionLocal, PullRequest, DevSkillProfile, init_db
from collections import defaultdict
import requests
import os
import re
from datetime import datetime
from pydantic import BaseModel

LLAMA_API_URL = "https://api.llama.com/v1/chat/completions"
LLAMA_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY")

author_prompts = {
    "synthesis_guidelines": """
You are an AI assistant helping engineering leaders understand developer skills and work styles based on their pull request history.

You will be provided with a batch of pre-processed pull request data for each developer. Each PR contains:
- Metadata (title, description, size, time to review, time to merge, commit count, timestamp, repo name)
- Tags: pr_type (feat, fix, etc.), domain_tag (domain/framework/others)
- A summary of the work done in the PR
- Skills identified in the PR with evidence
- Behavioral signal classifications on execution-exploration and scope-breadth axes

---

Your goal is to generate a `SkillProfile` JSON object with the following:

1. Developer Summary  
   Provide a 2–3 sentence overview summarizing their key strengths, focus areas, and contribution style.

2. Archetype Classification and Matrix Positioning
   Based on the behavioral signals across PRs, classify the developer into one of these four quadrants in the 2x2 matrix:
   
   - `high_output_executor`: Execution-oriented with broad scope. Gets things done fast across the board with versatility, high PR count, and quick turnarounds.
   - `domain_specialist`: Execution-oriented with specialized scope. Deep expert who crafts and polishes their realm with high craft and stability focus.
   - `polymath_generalist`: Exploration-oriented with broad scope. Jack-of-all-trades constantly learning with context-shifting, breadth-first approach.
   - `innovator_architect`: Exploration-oriented with specialized scope. Strategic thinker or creative experimenter focused on prototype-heavy, visionary systems.
   
   For each axis, categorize the developer's tendency:
   - Execution-Exploration axis: "strongly_execution", "moderately_execution", "balanced", "moderately_exploration", or "strongly_exploration"
   - Scope axis: "highly_specialized", "moderately_specialized", "balanced", "moderately_broad", or "very_broad"
   
   Include confidence level and supporting evidence for this classification.

3. Skill Classification
   Identify 5–15 skills from across the PRs and classify each into one of four categories:
   - `tech_stack`: Languages, frameworks, libraries, tools used in the implementation
   
   - `domain_expertise`: Understanding of specific business or product domains including:
     * Classic Business Domains: Financial systems, customer management, ecommerce, content systems, analytics, operations, marketing
     * Product-as-Domain: Developer tools, data systems, infrastructure, security
   
   - `architectural_and_systems_thinking`: Ability to understand and improve structure, scalability, and maintainability through:
     * Design patterns and abstractions
     * System-level considerations including critical path reliability
     * Technical debt management
     * Future-proofing
   
   - `behavioral_signals`: Work style patterns extracted from PRs along two axes:
     * Execution-Oriented vs. Exploration-Oriented 
     * Broad Scope vs. Specialized Scope

   For each skill, capture:
   - `name`: Clear, specific skill or trait (e.g., TypeScript, Cache Design, Authentication Systems)
   - `category`: One of the 4 listed above
   - `family`: Broader grouping (e.g., Frontend, Backend, API Design, DevOps, Collaboration)
   - `frequency`: Total across all PRs (sum of frequencies from individual PRs or newly calculated aggregate)
   - `unit`: Appropriate unit based on the skill category:
     * For tech_stack: "lines", "files", "modules"
     * For domain_expertise: "features", "components", "domain_concepts", "implementations"
     * For architectural_and_systems_thinking: "components", "patterns", "abstractions", "system_enhancements", "modules"
     * For behavioral_signals: "implementations", "iterations", "comments", "decisions"
   - `proficiency_confidence`: Float from 0 to 1 based on consistency and quality of evidence
   - `evidence`: Textual explanation with examples from multiple PRs

Aggregation Tips:
- Aggregate skills across all PRs: Mention each skill only once, even if it appears in multiple PRs.
- For frequency, sum the relevant metrics. For example, sum the lines of code for a tech stack skill across all PRs.
- Consider pluralizing units when aggregating across multiple PRs (e.g., "features" instead of "feature").
- Weigh both recurrence and significance:
  - Higher confidence if the skill appears consistently across multiple PRs, repos, or types of tasks.
  - High proficiency can still be assigned for a single, high-impact use case — if the skill was applied in a clearly advanced or innovative way.
- Assign proficiency based on peak demonstration:
  - If a developer shows multiple instances of a skill, choose the strongest observed usage
    (most complex, thoughtful, or optimized implementation) as the basis for scoring.
- Incorporate context diversity:
   - Confidence increases if the skill is demonstrated in different modules, projects,
    or under varying constraints (e.g., new feature + refactor + bugfix using same skill).
- Use evidence quality to tune confidence:
   - Boost confidence for skills supported by:
     * Clear PR descriptions explaining rationale
     * Complex diffs or abstractions
     * Reviewer praise or low review friction
   - Lower confidence for:
     * Skills seen only in minor or trivial changes
     * Lack of supporting commentary or unclear code quality
- Cap number of reported skills (e.g., 5–15) to avoid overfitting and focus on those with strongest support.


4. Matrix Positioning Evidence:
   Provide structured evidence to support the developer's classification in the 2x2 matrix:
   
   - Execution-Oriented vs. Exploration-Oriented evidence:
     * Collect concrete examples from PRs that demonstrate execution-oriented tendencies
     * Collect concrete examples from PRs that demonstrate exploration-oriented tendencies
     * Analyze which tendency is more prominent in their work
   
   - Specialized Scope vs. Broad Scope evidence:
     * Collect concrete examples from PRs that demonstrate specialized focus
     * Collect concrete examples from PRs that demonstrate broad scope across different areas
     * Analyze which tendency is more prominent in their work
   
   - Consistency analysis:
     * How consistent is the developer in their approach across different PRs?
     * Are there certain contexts where they shift their style?
     * Is there evidence of change in approach over time?

---

OUTPUT FORMAT
Return a valid JSON object of this exact structure:
type SkillProfile = {
  developer_name: string;
  summary: string; // 2-3 sentence overview of their contribution style and strengths
  
  archetype: {
    classification: "high_output_executor" | "domain_specialist" | "polymath_generalist" | "innovator_architect";
    confidence: number; // 0-1 scale
    evidence: string; // Supporting evidence from multiple PRs
    execution_exploration_tendency: "strongly_execution" | "moderately_execution" | "balanced" | "moderately_exploration" | "strongly_exploration";
    scope_tendency: "highly_specialized" | "moderately_specialized" | "balanced" | "moderately_broad" | "very_broad";
  };
  
  skill_profile: Skill[];
  
  matrix_evidence: {
    execution_evidence: string; // Concrete examples of execution-oriented behaviors from PRs
    exploration_evidence: string; // Concrete examples of exploration-oriented behaviors from PRs
    specialized_evidence: string; // Concrete examples of specialized scope focus from PRs
    broad_evidence: string; // Concrete examples of broad scope work from PRs
    consistency_analysis: string; // Analysis of how consistent these patterns are
  };
  
};

type Skill = {
  name: string; //one skill at a time
  category: "tech_stack" | "domain_expertise" | "architectural_and_systems_thinking" | "behavioral_signals";
  family: string;
  frequency: number; // Appropriate metric based on category, summed across all PRs
  unit: string; // Appropriate unit of measurement (pluralized when aggregating across PRs)
  confidence: number; // 0–1 scale (confidence in the evidence & frequency)
  evidence: string; // Examples from multiple PRs
};

Do not include any explanatory text, comments, or markdown. Only return the JSON.
"""
}

def get_developer_prs(developer: str) -> List[PullRequest]:
    print(f"[INFO] Fetching PRs for developer: {developer}")
    db = SessionLocal()
    try:
        prs = db.query(PullRequest).filter_by(developer=developer).all()
        print(f"[INFO] Found {len(prs)} PRs for developer '{developer}'.")
        return prs
    finally:
        db.close()

def aggregate_pr_metrics(prs: List[PullRequest]) -> Dict[str, Any]:
    print(f"[INFO] Aggregating PR metrics for {len(prs)} PRs...")
    total_prs = len(prs)
    total_lines = 0
    total_time_to_review = 0
    total_time_to_merge = 0
    total_commits = 0
    valid_review_times = 0
    valid_merge_times = 0
    repos = set()
    contrib_dist = defaultdict(int)
    pr_analyses_for_llm = []

    for pr in prs:
        details = pr.details or {}
        metadata = details.get("direct_metadata", {})
        ai_analysis = details.get("ai_analysis", {}).get("work", {})

        additions = metadata.get("additions", 0)
        deletions = metadata.get("deletions", 0)
        total_lines += (additions + deletions)

        time_to_review = metadata.get("time_to_first_review")
        if time_to_review is not None:
            try:
                total_time_to_review += float(time_to_review)
                valid_review_times += 1
            except Exception:
                pass

        time_to_merge = metadata.get("time_to_merge")
        if time_to_merge is not None:
            try:
                total_time_to_merge += float(time_to_merge)
                valid_merge_times += 1
            except Exception:
                pass

        total_commits += metadata.get("number_of_commits", 0)
        repos.add(pr.repo_url)

        pr_type = ai_analysis.get("pr_type", "others")
        domain_tag = ai_analysis.get("domain_tag", "others")
        contrib_dist[pr_type] += 1
        contrib_dist[domain_tag] += 1

        pr_analyses_for_llm.append({
            "repository": pr.repo_url,
            "pr_number": pr.pr_number,
            "title": pr.title,
            "analysis": ai_analysis
        })

    avg_pr_size = total_lines / total_prs if total_prs else 0
    avg_time_to_review = total_time_to_review / valid_review_times if valid_review_times else None
    avg_time_to_merge = total_time_to_merge / valid_merge_times if valid_merge_times else None
    avg_commits_per_pr = total_commits / total_prs if total_prs else 0

    print(f"[INFO] Aggregation complete. Avg PR size: {avg_pr_size}, Avg time to review: {avg_time_to_review}, Avg time to merge: {avg_time_to_merge}, Avg commits/PR: {avg_commits_per_pr}")

    return {
        "total_prs_merged": total_prs,
        "avg_pr_size": round(avg_pr_size, 2),
        "avg_time_to_review_hours": round(avg_time_to_review, 2) if avg_time_to_review is not None else None,
        "avg_time_to_merge_hours": round(avg_time_to_merge, 2) if avg_time_to_merge is not None else None,
        "avg_commits_per_pr": round(avg_commits_per_pr, 2),
        "repos_contributed_to": sorted(list(repos)),
        "contribution_distribution": dict(contrib_dist),
        "pr_analyses_for_llm": pr_analyses_for_llm
    }

def extract_json_from_text(text):
    # Try to find the first {...} block in the text
    match = re.search(r'({.*})', text, re.DOTALL)
    if match:
        return match.group(1)
    return text  # fallback

def synthesize_developer_skills(pr_analyses_for_llm: List[Dict], synthesis_guidelines: str) -> Dict[str, Any]:
    print(f"[INFO] Preparing prompt for LLM with {len(pr_analyses_for_llm)} PR analyses...")
    prompt = author_prompts["synthesis_guidelines"] + "\n\n" + json.dumps(pr_analyses_for_llm, indent=2)
    payload = {
        "model": LLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 2048,
        "temperature": 0.7
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLAMA_API_KEY}"
    }
    print("[INFO] Sending request to Llama API...")
    response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=90)
    if response.status_code != 200:
        print(f"[ERROR] Llama API error: {response.status_code} {response.text}")
        raise Exception(f"Llama API error: {response.status_code} {response.text}")
    result = response.json()
    try:
        text_response = result["completion_message"]["content"]["text"]
        print("[INFO] LLM response received. Parsing JSON...")
        cleaned_text = text_response
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1]
        if "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[0]
        cleaned_text = cleaned_text.strip()
        cleaned_text = extract_json_from_text(cleaned_text)
        return json.loads(cleaned_text)
    except Exception as e:
        print(f"[ERROR] Llama response was not valid JSON: {result}. Error: {str(e)}")
        raise Exception(f"Llama response was not valid JSON: {result}. Error: {str(e)}")

class DevSkillProfileModel(BaseModel):
    developer: str
    repository_filters: Any = None
    skills: Dict[Any, Any]
    pr_count: int
    updated_at: str

    class Config:
        orm_mode = True

def pydantic_to_db_dev_profile(pydantic_obj: DevSkillProfileModel) -> DevSkillProfile:
    return DevSkillProfile(
        developer=pydantic_obj.developer,
        repository_filters=pydantic_obj.repository_filters,
        skills=pydantic_obj.skills,
        pr_count=pydantic_obj.pr_count,
        updated_at=pydantic_obj.updated_at
    )

def pydantic_from_db_dev_profile(db_obj: DevSkillProfile) -> DevSkillProfileModel:
    return DevSkillProfileModel(
        developer=db_obj.developer,
        repository_filters=db_obj.repository_filters,
        skills=db_obj.skills,
        pr_count=db_obj.pr_count,
        updated_at=db_obj.updated_at
    )

def store_dev_profile_in_db(profile: Dict[str, Any], developer: str, pr_count: int):
    session = SessionLocal()
    try:
        now = datetime.utcnow().isoformat()
        # Check if a profile already exists for this developer
        db_obj = session.query(DevSkillProfile).filter_by(developer=developer).first()
        pydantic_obj = DevSkillProfileModel(
            developer=developer,
            repository_filters=None,
            skills=profile,
            pr_count=pr_count,
            updated_at=now
        )
        if db_obj:
            # Update existing
            db_obj.skills = profile
            db_obj.pr_count = pr_count
            db_obj.updated_at = now
            session.commit()
            session.refresh(db_obj)
            print(f"[INFO] Updated existing DevSkillProfile for '{developer}'.")
        else:
            # Create new
            new_db_obj = pydantic_to_db_dev_profile(pydantic_obj)
            session.add(new_db_obj)
            session.commit()
            session.refresh(new_db_obj)
            print(f"[INFO] Created new DevSkillProfile for '{developer}'.")
    except Exception as e:
        print(f"[ERROR] Failed to store DevSkillProfile for '{developer}': {e}")
        session.rollback()
    finally:
        session.close()

def profile_developer(developer: str):
    prs = get_developer_prs(developer)
    if not prs:
        print(f"[WARN] No PRs found for developer '{developer}'.")
        return {"error": "No PRs found for this developer."}
    metrics = aggregate_pr_metrics(prs)
    llm_result = synthesize_developer_skills(metrics["pr_analyses_for_llm"], author_prompts["synthesis_guidelines"])
    profile = {
        "developer_name": developer,
        "summary": llm_result.get("summary", ""),
        "archetype": llm_result.get("archetype", {}),
        "skill_profile": llm_result.get("skill_profile", []),
        "matrix_evidence": llm_result.get("matrix_evidence", {}),
        "pr_metrics": {k: v for k, v in metrics.items() if k != "pr_analyses_for_llm"}
    }
    print(f"[INFO] Developer profile generated for '{developer}'. Writing to DB...")
    store_dev_profile_in_db(profile, developer, metrics["total_prs_merged"])
    return profile

if __name__ == "__main__":
    import argparse
    init_db()  # <-- Ensure all tables are created
    parser = argparse.ArgumentParser(description="Profile a developer's skills and archetype from analyzed PRs.")
    parser.add_argument("developer", type=str, help="Developer name (as stored in the DB, e.g., GitHub username)")
    args = parser.parse_args()

    profile = profile_developer(args.developer)
    print(json.dumps(profile, indent=2))
