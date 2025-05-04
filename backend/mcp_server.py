import json
from typing import List, Dict, Optional
from mcp.server.fastmcp import FastMCP
from db import SessionLocal, PullRequest, DevSkillProfile, init_db
from pr_profiler import analyze_pr, PRAnalysis
from dev_profiler import profile_developer, get_all_developers

mcp = FastMCP("skillsync")

@mcp.tool()
async def list_authors() -> List[Dict[str, str]]:
    """
    List all authors with their PR counts.
    """
    db = SessionLocal()
    try:
        authors = db.query(DevSkillProfile.developer, DevSkillProfile.pr_count).order_by(DevSkillProfile.developer).all()
        return [
            {"name": developer, "pr_count": pr_count}
            for developer, pr_count in authors if pr_count > 0
        ]
    finally:
        db.close()

@mcp.tool()
async def get_author_profile(author_name: str) -> Dict:
    """
    Get detailed profile for a specific author.
    """
    db = SessionLocal()
    try:
        profile = db.query(DevSkillProfile).filter_by(developer=author_name).first()
        if not profile:
            return {"error": "Author profile not found"}
        return {
            "developer": profile.developer,
            "skills": profile.skills,
            "pr_count": profile.pr_count,
            "updated_at": profile.updated_at
        }
    finally:
        db.close()

@mcp.tool()
async def get_author_prs(author_name: str, limit: int = 50) -> List[Dict]:
    """
    Get all PRs for a specific author.
    """
    db = SessionLocal()
    try:
        prs = db.query(PullRequest).filter_by(developer=author_name).order_by(PullRequest.id.desc()).limit(limit).all()
        return [
            {
                "title": pr.title,
                "repo": pr.repo_url,
                "number": pr.pr_number,
                "full_ref": f"{pr.repo_url}#{pr.pr_number}"
            }
            for pr in prs
        ]
    finally:
        db.close()

@mcp.tool()
async def get_pr_details(repo_url: str, pr_number: int) -> Dict:
    """
    Get detailed analysis for a specific PR.
    """
    db = SessionLocal()
    try:
        pr = db.query(PullRequest).filter_by(repo_url=repo_url, pr_number=pr_number).first()
        if not pr:
            return {"error": "PR not found"}
        return pr.details or {}
    finally:
        db.close()

@mcp.tool()
async def get_author_skills(author_name: str) -> Dict:
    """
    Get the skills profile for a specific author.
    """
    db = SessionLocal()
    try:
        profile = db.query(DevSkillProfile).filter_by(developer=author_name).first()
        if not profile:
            return {"error": "Author profile not found"}
        return profile.skills
    finally:
        db.close()

@mcp.prompt()
async def repetitive_work_analysis(author_name: str) -> str:
    """
    Analyze the repetitive work done by an author.
    """
    author_pr_data = await get_author_prs(author_name)
    author_skill_data = await get_author_skills(author_name)
    pr_data = json.dumps(author_pr_data)
    skill_data = json.dumps(author_skill_data)
    return f"""
    Analyze the repetitive work done by {author_name}.\n\nHighlight patterns in their PRs. Compare it to their skills and highlight whether they are being utilized to their fullest potential with respect to their skills.\n\nPR data: {pr_data}\nSkill data: {skill_data}\n\nReturn the analysis in a structured format.
    """

@mcp.prompt()
async def organization_repetitive_work_analysis() -> str:
    """
    Analyze repetitive work patterns across all authors in the organization.
    """
    authors = await list_authors()
    author_analyses = []
    for author_data in authors:
        author_name = author_data["name"]
        pr_data = await get_author_prs(author_name)
        skill_data = await get_author_skills(author_name)
        author_analyses.append({
            "name": author_name,
            "pr_count": author_data["pr_count"],
            "prs": pr_data,
            "skills": skill_data
        })
    analysis_data = json.dumps(author_analyses)
    return f"""
    Analyze the repetitive work patterns across the entire organization.\n\nFor each author, examine their PR patterns and skills to identify:\n1. Common types of work being done repeatedly\n2. Skills that might be underutilized\n3. Potential opportunities for work redistribution based on skills\n4. Areas where automation could reduce repetitive tasks\n\nOrganization-wide data: {analysis_data}\n\nPlease provide:\n1. Individual author summaries\n2. Organization-wide patterns\n3. Recommendations for improving skill utilization\n4. Suggestions for reducing repetitive work through process improvements or automation
    """

if __name__ == "__main__":
    import sys
    arg1 = sys.argv[1] if len(sys.argv) > 1 else None
    if arg1 == "test":
        import asyncio
        print(asyncio.run(list_authors()))
    else:
        print("[MCP SERVER] MCP server started successfully and is ready for requests.")
        mcp.run("stdio") 