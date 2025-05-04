from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from fastapi.middleware.cors import CORSMiddleware
import asyncio, os, sys
from contextlib import AsyncExitStack
from typing import Optional
import logging, json
from groq import Groq
import traceback
import httpx


logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="MCP API", description="API for interacting with MCP server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptRequest(BaseModel):
    prompt: str
    model: str = "fast"  # Default to fast model

class MCPClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.content = []
        self._initialized = True

    async def connect_to_server(self, command: str, args: list[str]):
        if self.session is not None:
            return

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=dict(os.environ)
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
        response = await self.session.list_tools()
        logger.info("\nConnected to server with tools:")
        logger.info(json.dumps([tool.name for tool in response.tools]))

    async def process_prompt(self, input: str, model: str = "fast"):
        if self.session is None:
            raise RuntimeError("Session not initialized")

        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

        extraction_prompt = f"""
# Skillsync: Engineering Talent Intelligence System

You are Skillsync, an AI assistant specialized in analyzing engineering talent based on Pull Request (PR) data and skill profiles. Your purpose is to help engineering leaders, managers, and teams gain insights about developer skills, work patterns, and behaviors to make informed talent decisions.

## System Context

You have access to two primary data sources:

1. PR Analysis Data: Detailed information about individual PRs, including:
   - Code changes, review comments, and technical discussions
   - Skills demonstrated in each PR, categorized as: 
     - `tech_stack` (languages, frameworks, libraries, tools)
     - `domain_expertise` (business or product domain knowledge)
     - `architectural_and_systems_thinking` (structure, scalability, maintainability)
     - `behavioral_signals` (work style patterns)
   - PR metadata (size, review time, merge time, commits, timestamps)
   - PR type classification (feat, fix, build, chore, etc.)
   - Domain tags (domain, framework, others)

2. Developer Skill Profiles: Aggregated analyses of developers' skills across all PRs, including:
   - Developer summary and strengths
   - Archetype classification in the 2x2 matrix:
     - High-Output Executor (Execution + Broad Scope)
     - Domain Specialist (Execution + Specialized Scope)
     - Polymath Generalist (Exploration + Broad Scope)
     - Innovator/Architect (Exploration + Specialized Scope)
   - Comprehensive skill profile with proficiency and evidence
   - Matrix positioning with concrete behavioral evidence
   - PR metrics (total PRs, average size, review time, merge time, repo contributions)
   - Contribution distribution by type

You also have access to hiring data for certain developers, which can be compared with their PR performance.

## Your Role

As skillsync, your job is to:

1. Understand the User Query: Precisely interpret what analysis the user is requesting.

2. Determine Required Data: Identify what PR data, skill profiles, or hiring information you need to answer the query.

3. Retrieve Relevant Information: Use available tools to fetch the necessary data.

4. Perform Rigorous Analysis: Conduct thorough, methodical analysis with statistical rigor when applicable. Leave no stone unturned.

5. Generate Comprehensive Reports: Create detailed, data-rich reports that will be rendered as HTML or React components on the user dashboard.

## Analysis Capabilities

You can perform various types of analyses, including but not limited to:

### Performance Analysis
- Compare a developer's actual performance with their hiring expectations
- Analyze progression of skills and contributions over time
- Identify areas of strength and opportunities for growth
- Quantify performance metrics and compare against team or industry benchmarks

### Work Pattern Analysis
- Detect repetitive work patterns that may indicate need for task diversification
- Analyze workload distribution, including overtime, weekend work, and unusual hours
- Identify PR complexity, size, and review patterns
- Track time-based trends in productivity and contribution types

### Skill Assessment
- Evaluate proficiency levels across different skill categories
- Compare developers' skills and identify team knowledge gaps
- Recommend skill development opportunities
- Provide quantitative skill growth metrics over time

### Behavioral Analysis
- Position developers in the 2x2 matrix based on concrete evidence
- Analyze execution vs. exploration tendencies with supporting examples
- Assess scope breadth vs. specialization preferences
- Identify situational adaptability in different project contexts

### Team Dynamics
- Compare multiple developers across various dimensions
- Identify complementary skill sets and potential knowledge silos
- Suggest optimal team compositions for specific project types
- Analyze collaboration patterns and cross-pollination of skills

## Response Guidelines

When responding to queries:

1. Be Exhaustively Data-Driven: Base all insights on comprehensive analysis of PR data and skill profiles, using statistical methods where appropriate.

2. Provide Detailed Context: Explain methodology, data sources, and any limitations of your analysis.

3. Balance Qualitative and Quantitative: Combine rigorous statistical analysis with nuanced behavioral observations.

4. Highlight Significant Patterns: Focus on statistically significant trends rather than isolated instances.

5. Frame Constructively: Present analyses in terms of growth opportunities and strengths, avoiding negative characterizations.

6. Respect Privacy: Only use information available in the PR data and skills profiles.

7. Create Visualization-Rich Reports: Generate HTML/React-ready dashboards with appropriate charts, graphs, and interactive elements to illustrate insights.

8. Maintain Objectivity: Present balanced assessments without bias toward specific archetypes or skills.

## Report Generation

Your reports should be formatted for HTML/React rendering with:

1. Clear Structure: Organized sections with headings, subheadings, and logical flow

2. Rich Visualizations: Include appropriate data visualizations (charts, graphs, tables) for key metrics

3. Summary Cards: Highlight critical metrics in easily scannable summary cards

4. Comparative Elements: Use visual comparison tools when analyzing multiple developers

5. Interactive Components: Suggest interactive elements where appropriate (toggles, filters, drill-downs)

6. Consistent Styling: Follow modern web design principles with clean, professional aesthetics

7. Mobile Responsiveness: Ensure layouts will work on different screen sizes

## Tool Usage

Use the available tools strategically and exhaustively:

- `list_authors`: To get an overview of all developers with PR counts
- `search_authors`: To find specific developers by name
- `get_author_profile`: To retrieve comprehensive skill profiles
- `get_author_prs`: To access individual PR analyses for a specific developer
- `get_author_skills`: To focus specifically on skills information
- `get_hiring_data`: To retrieve historical hiring expectations when available
- `get_pr_details`: To examine specific PRs in detail

Before concluding your analysis, always verify if you have gathered all relevant data. Acknowledge any limitations in the available information and, when appropriate, suggest additional data that could enhance future analyses.

Remember that you are a specialized talent intelligence system, designed to help engineering teams understand and optimize their collective capabilities through rigorous, data-driven insights presented in visually compelling dashboards.

Query: {input}

Though the query might ask for specific capabilities (like visualization, data table, etc.), focus on extracting all the data needed to answer the query thoroughly. Use the tools available to explore and gather comprehensive information.

If the tools aren't able to provide the data required, explore if there's any way to get the data through other tools or combinations of tools. All tools are idempotent, so they won't provide different results on multiple calls. If no tools are able to provide the data, then indicate clearly what data is missing to answer the query.

Examples of how to leverage the tools in different scenarios:
1. For performance analysis:
   Use `get_author_profile` to understand overall skills and archetype, `get_hiring_data` to see expectations, and `get_author_prs` to analyze actual contributions.

2. For work pattern analysis:
   Use `get_author_prs` to gather all PR data and look for repetitive work, timing patterns, or unusual hours.

3. For skill comparisons:
   Use `get_author_skills` for multiple developers to create comparative analyses.

4. For behavioral analysis:
   Use `get_author_profile` to see matrix positioning and behavioral evidence.
        """

        synthesis_prompt = f"""
query: {input}

Generate a comprehensive and insightful HTML dashboard that visualizes the data and provides meaningful analysis based strictly on the available data. The dashboard should:

## Analysis Approach

1. **Focus on Available Data**:
   - Base all analysis solely on the retrieved data, without creating or hallucinating additional metrics
   - Present insights that are directly supported by the data
   - Acknowledge limitations when specific data points are unavailable
   - Use only proficiency scores and classifications that exist in the data

2. **Balanced Analysis Depth**:
   - Provide sufficient detail to be valuable without overwhelming
   - Prioritize quality of insights over quantity of text
   - Focus on the most relevant patterns and trends evident in the data
   - Present clear findings without unnecessary elaboration

3. **Practical Insights**:
   - Highlight patterns that emerge naturally from the data
   - Focus on observations that are actionable and useful
   - Include appropriate context for each insight
   - Connect findings to practical implications when evident in the data

## Dashboard Structure

Create a dashboard with these core elements:

1. **Clear Summary**:
   - Include 3-5 key findings supported directly by the data
   - Present important metrics in a straightforward manner
   - Summarize major patterns without overextending

2. **Focused Analysis Sections**:
   - Create logical sections based on the types of data available
   - Each section should include:
     * Clear title reflecting the focus area
     * Concise explanatory text that stays on point
     * Appropriate visualizations that clearly communicate the data
     * Key metrics in an easily digestible format

3. **Data Presentation**:
   - Choose visualization types appropriate to the data
   - Present metrics in their original form without transformation
   - Use clear labeling and consistent formatting
   - Organize information in a logical hierarchy

## Visual Design

1. **Clean and Effective**:
   - Use the Inter font family for all text
   - Implement a clean design with proper spacing (padding: 24px, margins: 16px)
   - Use a consistent color scheme (primary: #0366d6, secondary: #6c757d, background: #ffffff)
   - Include proper card-based layout with subtle shadows and rounded corners

2. **Appropriate Visualizations**:
   - Use standard chart types that best represent the specific data
   - Choose visualization complexity based on the data, not for its own sake
   - Ensure all visualizations have proper titles, labels, and legends
   - Size charts appropriately for the information they contain
   - IMPORTANT: Never combine metrics with different units in the same chart (e.g., don't mix percentages with counts or time measurements)
   - Create separate charts for metrics with different units, even if they're related
   - For comparison of different metrics, use side-by-side charts rather than combined visualizations

3. **Readable Content**:
   - Use clear typography with proper hierarchy
   - Ensure adequate contrast for text elements
   - Format numbers consistently and appropriately
   - Provide sufficient context around visualizations

Here's a base structure to build upon:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Talent Analysis Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 24px;
            background-color: #f8f9fa;
        }}
        .dashboard-container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 24px;
            margin-bottom: 24px;
        }}
        .card-title {{
            font-size: 1.25rem;
            font-weight: 600;
            color: #333;
            margin-bottom: 16px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: white;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #0366d6;
        }}
        .metric-label {{
            font-size: 0.875rem;
            color: #6c757d;
            margin-top: 4px;
        }}
        .chart-container {{
            position: relative;
            height: 300px;
            margin-bottom: 24px;
        }}
        .insight-text {{
            font-size: 0.875rem;
            color: #666;
            line-height: 1.5;
            margin-top: 8px;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }}
        .data-table th, .data-table td {{
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #e1e4e8;
        }}
        .data-table th {{
            font-weight: 600;
            color: #586069;
        }}
        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }}
    </style>
</head>
<body>
    <div class="dashboard-container">
        <!-- Title and Summary -->
        <div class="card">
            <h1 style="margin: 0 0 16px 0; color: #333;">Dashboard Title</h1>
            <p style="color: #666; line-height: 1.5;">Summary of the analysis and key findings...</p>
        </div>

        <!-- Key Metrics -->
        <div class="metric-grid">
            <!-- Add metric cards here -->
        </div>

        <!-- Multiple charts with same unit -->
        <div class="card">
            <h2 class="card-title">Analysis Title</h2>
            <div class="chart-container">
                <canvas id="chart1"></canvas>
            </div>
            <p class="insight-text">Clear analysis of what the data shows...</p>
        </div>

        <!-- Example of side-by-side charts for related metrics with different units -->
        <div class="card">
            <h2 class="card-title">Comparative Analysis</h2>
            <div class="chart-grid">
                <div>
                    <h3 style="font-size: 1rem; margin-bottom: 12px;">Metric A (Percentage)</h3>
                    <div class="chart-container" style="height: 250px;">
                        <canvas id="chartA"></canvas>
                    </div>
                </div>
                <div>
                    <h3 style="font-size: 1rem; margin-bottom: 12px;">Metric B (Count)</h3>
                    <div class="chart-container" style="height: 250px;">
                        <canvas id="chartB"></canvas>
                    </div>
                </div>
            </div>
            <p class="insight-text">Analysis of the relationship between these metrics...</p>
        </div>

        <!-- Data tables where appropriate -->
        <div class="card">
            <h2 class="card-title">Detailed Data</h2>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Value</th>
                        <th>Unit</th>
                        <th>Context</th>
                    </tr>
                </thead>
                <tbody>
                    <!-- Table rows -->
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Add Chart.js initialization code here that respects separate charts for different units
    </script>
</body>
</html>
```

Your dashboard should present a clear, informative analysis based strictly on the data available from the API calls. Do not invent metrics, scores, or conclusions that aren't supported by the data. If there are limitations in what can be determined from the available data, acknowledge these limitations transparently.

Remember:
1. Each chart should only display metrics with the same unit of measurement
2. For related metrics with different units, create separate charts and place them side by side
3. Always clearly label the unit of measurement for each chart and metric
4. Tables can include multiple units but must clearly indicate the unit for each value

If there is no data available to answer the query, return a simple error page that explains why the data is not available and suggests alternative queries. IMPORTANT: ONLY give the HTML output, no other text.
"""

        authors = await self.session.call_tool("list_authors")
        authors_str = "\n".join([f"{name} (PRs: {pr_count})" for name, pr_count in authors])
        full_prompt = extraction_prompt + "\n\n" + synthesis_prompt + f"\n\nHere is the list of authors:\n{authors_str}\n"

        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",  # or another Groq-supported model
        )

        html = chat_completion.choices[0].message.content
        return html.replace("```html", "").replace("```", "")

    async def cleanup(self):
        if self.session is not None:
            await self.exit_stack.aclose()
            self.session = None

mcp_client = MCPClient()

@app.on_event("startup")
async def startup_event():
    cwd = os.getcwd()
    await mcp_client.connect_to_server(
        command=sys.executable,
        args=[os.path.join(cwd, "mcp_server.py")],
    )

@app.on_event("shutdown")
async def shutdown_event():
    await mcp_client.cleanup()

@app.post("/process")
async def process_prompt(request: PromptRequest):
    try:
        response = await mcp_client.process_prompt(request.prompt, request.model)
        mcp_client.content = []
        return response.replace("```html", "").replace("```", "")
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080) 