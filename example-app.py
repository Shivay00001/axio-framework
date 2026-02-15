"""
Axiom DSL Example: Financial Intelligence Platform

This is a complete example showing all major features of Axiom:
- Agent definitions with reasoning
- Memory schemas (vector + graph)
- MCP tool integration
- UI views with state management
- API routes
- Multi-agent workflows
- Security configuration
"""

from axiom import App, Agent, View, Action, Workflow, Step, Task
from axiom.ui import (
    Container, Row, Column, Card, DataTable, Button, 
    Chart, Form, Input, Select, Markdown, Tabs, TabPanel
)
from axiom.mcp import MCPTool
from axiom.memory import MemorySchema, Vector, Graph
from axiom.auth import SecurityConfig, RequirePermission
from axiom.types import RequestContext
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel

# ============================================================================
# APPLICATION CONFIGURATION
# ============================================================================

app = App(
    name="financial_analyst",
    version="2.1.0",
    description="AI-powered financial analysis platform",
    config={
        # Agent Runtime Configuration
        "agents": {
            "enabled": True,
            "default_model": "claude-sonnet-4",
            "max_concurrent": 10,
            "timeout": 300  # seconds
        },
        
        # MCP Server Configuration
        "mcp_servers": {
            "filesystem": {
                "protocol": "stdio",
                "command": "node",
                "args": ["./mcp-servers/filesystem/index.js"]
            },
            "github": {
                "protocol": "sse",
                "url": "https://api.github-mcp.com/v1",
                "auth": {"token": "$GITHUB_TOKEN"}
            },
            "postgres": {
                "protocol": "stdio",
                "command": "python",
                "args": ["./mcp-servers/postgres/server.py"]
            },
            "web_search": {
                "protocol": "sse",
                "url": "https://api.search-mcp.com/v1",
                "auth": {"api_key": "$SEARCH_API_KEY"}
            }
        },
        
        # Memory Configuration
        "memory": {
            "backend": "hybrid",  # vector + graph + cache
            "vector": {
                "provider": "pgvector",
                "connection_string": "$POSTGRES_URL",
                "embedding_model": "text-embedding-3-large",
                "embedding_dims": 1536
            },
            "graph": {
                "provider": "neo4j",
                "connection_string": "$NEO4J_URL"
            },
            "cache": {
                "provider": "redis",
                "connection_string": "$REDIS_URL",
                "ttl": 3600
            }
        },
        
        # Security Configuration
        "security": SecurityConfig(
            auth_provider="clerk",
            jwt_secret="$JWT_SECRET",
            rbac_enabled=True,
            api_rate_limit="1000/hour",
            agent_rate_limit="100/hour"
        )
    }
)

# ============================================================================
# DATA MODELS
# ============================================================================

class Company(BaseModel):
    id: str
    name: str
    ticker: str
    sector: str
    market_cap: float
    website: str

class CompanyAnalysis(BaseModel):
    company_id: str
    analysis_type: Literal["financial", "technical", "competitive", "comprehensive"]
    summary: str
    metrics: dict
    insights: list[str]
    risks: list[str]
    opportunities: list[str]
    confidence_score: float
    timestamp: datetime

class MarketPosition(BaseModel):
    company_id: str
    competitors: list[str]
    market_share: float
    growth_rate: float
    positioning: str

# ============================================================================
# MEMORY SCHEMAS
# ============================================================================

@app.memory_schema
class CompanyIntelligence(MemorySchema):
    """Memory schema for storing company research data"""
    
    company_id: str
    company_name: str
    
    # Text content for embedding
    documents: list[str]
    
    # Vector embeddings for semantic search
    embeddings: Vector(dims=1536)
    
    # Graph relationships
    relationships: Graph(
        nodes=["Company", "Executive", "Product", "Competitor", "Investor"],
        edges=[
            "owns", "manages", "develops", "competes_with", 
            "invested_in", "partners_with", "acquired"
        ]
    )
    
    # Structured data
    financial_data: dict
    market_data: dict
    technical_data: dict
    
    # Metadata
    last_updated: datetime
    sources: list[str]
    confidence: float

# ============================================================================
# AGENT DEFINITIONS
# ============================================================================

@app.agent(
    name="research_agent",
    model="claude-sonnet-4",
    memory=CompanyIntelligence,
    tools=[
        MCPTool("github", "search_code"),
        MCPTool("github", "get_repository"),
        MCPTool("web_search", "search"),
        MCPTool("postgres", "query"),
        MCPTool("filesystem", "read_file")
    ],
    reasoning={
        "max_iterations": 15,
        "reflection_enabled": True,
        "tool_parallelism": True,
        "temperature": 0.1
    }
)
class ResearchAgent:
    """Agent that performs deep company technical analysis"""
    
    async def analyze_company(
        self,
        company_id: str,
        analysis_type: Literal["financial", "technical", "competitive"]
    ) -> CompanyAnalysis:
        """
        Perform comprehensive company analysis
        
        This method demonstrates Axiom's reasoning loop:
        1. Retrieve context from memory
        2. Use MCP tools to gather fresh data
        3. Agent decides what to do next based on findings
        4. Store results back to memory
        """
        
        # Step 1: Retrieve existing knowledge from memory
        memory_context = await self.memory.recall(
            query=f"company {company_id} {analysis_type} analysis",
            k=10,
            strategy="hybrid"  # Use vector + graph search
        )
        
        # Step 2: Get company basic info from database
        company_info = await self.tools.postgres.query(
            sql=f"""
                SELECT * FROM companies 
                WHERE id = '{company_id}'
            """
        )
        
        if not company_info:
            raise ValueError(f"Company not found: {company_id}")
        
        company = Company(**company_info[0])
        
        # Step 3: Gather technical data (GitHub activity)
        github_repos = await self.tools.github.search_code(
            query=f"org:{company.name.lower().replace(' ', '-')}"
        )
        
        # Step 4: Search web for recent news
        recent_news = await self.tools.web_search.search(
            query=f"{company.name} {analysis_type} analysis news"
        )
        
        # Step 5: AI reasoning loop
        # The agent analyzes all gathered data and produces insights
        analysis = await self.reason(
            objective=f"""
                Perform {analysis_type} analysis for {company.name}.
                
                Consider:
                - Historical data from memory
                - Current GitHub activity
                - Recent news and market sentiment
                - Financial metrics from database
                
                Provide:
                - Executive summary
                - Key metrics
                - Insights (minimum 5)
                - Risks (minimum 3)
                - Opportunities (minimum 3)
                - Confidence score (0-1)
            """,
            context={
                "memory": memory_context,
                "company": company.dict(),
                "github_activity": github_repos,
                "recent_news": recent_news
            }
        )
        
        # Step 6: Store new insights in memory
        await self.memory.store(
            CompanyIntelligence(
                company_id=company_id,
                company_name=company.name,
                documents=[analysis.summary] + analysis.insights,
                embeddings=await self.embed(analysis.summary),
                relationships={
                    "nodes": [
                        {"type": "Company", "id": company_id, "name": company.name}
                    ],
                    "edges": []  # Will be populated by graph extraction
                },
                financial_data={},
                market_data={},
                technical_data={"github_repos": len(github_repos)},
                last_updated=datetime.now(),
                sources=[f"github:{len(github_repos)}", f"news:{len(recent_news)}"],
                confidence=analysis.confidence_score
            )
        )
        
        return analysis
    
    async def compare_companies(
        self,
        company_ids: list[str],
        criteria: list[str]
    ) -> dict:
        """Compare multiple companies across specified criteria"""
        
        # Parallel analysis of multiple companies
        analyses = await self.parallel_execute([
            self.analyze_company(cid, "comprehensive")
            for cid in company_ids
        ])
        
        # Reasoning to synthesize comparison
        comparison = await self.reason(
            objective=f"""
                Compare these companies across: {', '.join(criteria)}
                Provide a structured comparison table and summary.
            """,
            context={"analyses": [a.dict() for a in analyses]}
        )
        
        return comparison

@app.agent(
    name="market_agent",
    model="claude-sonnet-4",
    memory=CompanyIntelligence,
    tools=[
        MCPTool("web_search", "search"),
        MCPTool("postgres", "query")
    ],
    reasoning={
        "max_iterations": 10,
        "temperature": 0.2
    }
)
class MarketAgent:
    """Agent specialized in market positioning and competitive analysis"""
    
    async def analyze_market_position(
        self,
        company_id: str
    ) -> MarketPosition:
        """Analyze company's market position and competitive landscape"""
        
        # Get company info
        company_info = await self.tools.postgres.query(
            sql=f"SELECT * FROM companies WHERE id = '{company_id}'"
        )
        company = Company(**company_info[0])
        
        # Search for competitors
        competitors_data = await self.tools.web_search.search(
            query=f"{company.name} competitors {company.sector}"
        )
        
        # Get market data
        market_data = await self.tools.postgres.query(
            sql=f"""
                SELECT * FROM market_data 
                WHERE sector = '{company.sector}'
                ORDER BY date DESC LIMIT 10
            """
        )
        
        # Analyze with reasoning
        position = await self.reason(
            objective=f"""
                Analyze market position for {company.name}.
                Identify main competitors, estimate market share,
                assess competitive advantages.
            """,
            context={
                "company": company.dict(),
                "competitors": competitors_data,
                "market_data": market_data
            }
        )
        
        return position

@app.agent(
    name="synthesis_agent",
    model="claude-opus-4",  # Use more powerful model for synthesis
    reasoning={
        "max_iterations": 8,
        "temperature": 0.15
    }
)
class SynthesisAgent:
    """Agent that synthesizes insights from multiple sources"""
    
    async def synthesize_reports(
        self,
        technical_analysis: CompanyAnalysis,
        market_analysis: MarketPosition,
        sentiment_data: dict
    ) -> CompanyAnalysis:
        """Synthesize multiple analyses into comprehensive report"""
        
        comprehensive = await self.reason(
            objective="""
                Synthesize all analyses into a comprehensive report.
                Identify patterns, contradictions, and high-confidence insights.
                Provide actionable recommendations.
            """,
            context={
                "technical": technical_analysis.dict(),
                "market": market_analysis.dict(),
                "sentiment": sentiment_data
            }
        )
        
        return comprehensive

# ============================================================================
# MULTI-AGENT WORKFLOWS
# ============================================================================

@app.workflow(name="comprehensive_analysis")
class ComprehensiveAnalysisWorkflow(Workflow):
    """Orchestrate multiple agents for comprehensive company analysis"""
    
    steps = [
        # Step 1: Parallel data gathering
        Step(
            name="parallel_research",
            parallel=True,
            agents={
                "research_agent": Task(
                    method="analyze_company",
                    args={
                        "company_id": "$input.company_id",
                        "analysis_type": "technical"
                    }
                ),
                "market_agent": Task(
                    method="analyze_market_position",
                    args={"company_id": "$input.company_id"}
                ),
                # Can add more agents here
            }
        ),
        
        # Step 2: Sequential synthesis
        Step(
            name="synthesis",
            parallel=False,
            agents={
                "synthesis_agent": Task(
                    method="synthesize_reports",
                    args={
                        "technical_analysis": "$steps.parallel_research.research_agent",
                        "market_analysis": "$steps.parallel_research.market_agent",
                        "sentiment_data": {}  # Would come from sentiment agent
                    }
                )
            }
        )
    ]

# ============================================================================
# UI VIEWS
# ============================================================================

@app.view(route="/", auth_required=False)
class LandingPage(View):
    """Public landing page"""
    
    def layout(self):
        return Container([
            Row([
                Column(width=12, children=[
                    Card([
                        Markdown("""
                        # Financial Intelligence Platform
                        
                        AI-powered company analysis and market research.
                        """)
                    ])
                ])
            ])
        ])

@app.view(route="/dashboard", auth_required=True)
class Dashboard(View):
    """Main dashboard for authenticated users"""
    
    # State definition (compiles to React state)
    state = {
        "companies": list[Company],
        "selected_company": Optional[Company],
        "analysis": Optional[CompanyAnalysis],
        "loading": bool,
        "analysis_type": str,
        "tab": str
    }
    
    # Initial state
    initial_state = {
        "companies": [],
        "selected_company": None,
        "analysis": None,
        "loading": False,
        "analysis_type": "technical",
        "tab": "overview"
    }
    
    def layout(self):
        return Container([
            # Header
            Row([
                Column(width=12, children=[
                    Card([
                        Markdown("# Financial Analysis Dashboard")
                    ])
                ])
            ]),
            
            # Main content
            Row([
                # Left sidebar - Company list
                Column(width=4, children=[
                    Card([
                        Markdown("## Companies"),
                        DataTable(
                            data=self.state.companies,
                            columns=["name", "ticker", "sector", "market_cap"],
                            on_select=self.handle_select_company,
                            searchable=True,
                            sortable=True,
                            page_size=20
                        )
                    ])
                ]),
                
                # Right content - Analysis
                Column(width=8, children=[
                    # Show only when company selected
                    self.if_condition(
                        condition=self.state.selected_company,
                        then_content=[
                            Card([
                                Markdown(f"## {self.state.selected_company.name if self.state.selected_company else ''}"),
                                
                                # Analysis type selector
                                Row([
                                    Column(width=6, children=[
                                        Select(
                                            value=self.state.analysis_type,
                                            options=[
                                                {"label": "Technical", "value": "technical"},
                                                {"label": "Financial", "value": "financial"},
                                                {"label": "Competitive", "value": "competitive"}
                                            ],
                                            on_change=self.handle_analysis_type_change
                                        )
                                    ]),
                                    Column(width=6, children=[
                                        Button(
                                            text="Run Analysis",
                                            on_click=self.trigger_analysis,
                                            loading=self.state.loading,
                                            variant="primary",
                                            size="large"
                                        )
                                    ])
                                ])
                            ]),
                            
                            # Analysis results
                            self.if_condition(
                                condition=self.state.analysis,
                                then_content=[
                                    Tabs(
                                        value=self.state.tab,
                                        on_change=self.handle_tab_change,
                                        tabs=[
                                            TabPanel(
                                                label="Overview",
                                                value="overview",
                                                content=Card([
                                                    Markdown(f"## Summary\n\n{self.state.analysis.summary if self.state.analysis else ''}")
                                                ])
                                            ),
                                            TabPanel(
                                                label="Metrics",
                                                value="metrics",
                                                content=Card([
                                                    Chart(
                                                        type="bar",
                                                        data=self.state.analysis.metrics if self.state.analysis else {}
                                                    )
                                                ])
                                            ),
                                            TabPanel(
                                                label="Insights",
                                                value="insights",
                                                content=Card([
                                                    Markdown(
                                                        "\n".join([f"- {i}" for i in self.state.analysis.insights])
                                                        if self.state.analysis else ""
                                                    )
                                                ])
                                            )
                                        ]
                                    )
                                ]
                            )
                        ]
                    )
                ])
            ])
        ])
    
    # Actions (compile to API calls + state updates)
    @Action(debounce=300)
    async def handle_select_company(self, company: Company):
        """Handle company selection"""
        self.state.selected_company = company
        self.state.analysis = None
        self.state.tab = "overview"
    
    @Action
    async def handle_analysis_type_change(self, value: str):
        """Handle analysis type change"""
        self.state.analysis_type = value
    
    @Action
    async def handle_tab_change(self, value: str):
        """Handle tab change"""
        self.state.tab = value
    
    @Action
    async def trigger_analysis(self):
        """Trigger analysis for selected company"""
        self.state.loading = True
        
        # Call agent directly
        agent = self.app.agents.research_agent
        analysis = await agent.analyze_company(
            company_id=self.state.selected_company.id,
            analysis_type=self.state.analysis_type
        )
        
        self.state.analysis = analysis
        self.state.loading = False
    
    # Lifecycle hooks
    async def on_mount(self):
        """Load companies when view mounts"""
        # This compiles to useEffect in React
        companies = await self.api.get("/api/companies")
        self.state.companies = companies

# ============================================================================
# API ROUTES
# ============================================================================

@app.api("/api/companies", methods=["GET"])
async def list_companies(ctx: RequestContext):
    """List all companies"""
    
    # No auth required, but rate limited
    async with ctx.rate_limit(key=f"ip:{ctx.request.client.host}"):
        companies = await ctx.db.query(
            "SELECT * FROM companies ORDER BY market_cap DESC LIMIT 100"
        )
        return companies

@app.api("/api/companies/{company_id}", methods=["GET"])
@RequirePermission("read:company")
async def get_company(company_id: str, ctx: RequestContext):
    """Get single company details"""
    
    company = await ctx.db.query(
        "SELECT * FROM companies WHERE id = $1",
        company_id
    )
    
    if not company:
        raise ctx.http_exception(404, "Company not found")
    
    return company[0]

@app.api("/api/companies/{company_id}/analyze", methods=["POST"])
@RequirePermission("analyze:company")
async def analyze_company_endpoint(
    company_id: str,
    analysis_type: str,
    ctx: RequestContext
):
    """Trigger company analysis"""
    
    # Rate limit per user
    async with ctx.rate_limit(key=f"user:{ctx.user.id}", limit="100/hour"):
        # Get agent instance
        agent = ctx.app.agents.research_agent
        
        # Execute analysis
        result = await agent.analyze_company(
            company_id=company_id,
            analysis_type=analysis_type
        )
        
        # Log execution
        await ctx.audit_log.log(
            action="agent_execution",
            agent="research_agent",
            user_id=ctx.user.id,
            metadata={"company_id": company_id, "analysis_type": analysis_type}
        )
        
        return result

@app.api("/api/workflows/comprehensive-analysis", methods=["POST"])
@RequirePermission("execute:workflow")
async def run_comprehensive_analysis(
    company_id: str,
    ctx: RequestContext
):
    """Run comprehensive multi-agent analysis workflow"""
    
    workflow = ctx.app.workflows.comprehensive_analysis
    
    result = await workflow.execute(
        inputs={"company_id": company_id},
        context=ctx
    )
    
    return result

# ============================================================================
# INITIALIZATION & STARTUP
# ============================================================================

@app.on_startup
async def initialize():
    """Run on application startup"""
    
    print("Initializing Axiom application...")
    
    # Initialize memory backends
    await app.memory.initialize()
    
    # Connect to MCP servers
    await app.mcp.connect_all()
    
    # Run database migrations
    await app.db.migrate()
    
    print("Application ready!")

@app.on_shutdown
async def cleanup():
    """Run on application shutdown"""
    
    print("Shutting down...")
    
    # Close MCP connections
    await app.mcp.disconnect_all()
    
    # Close database connections
    await app.db.close()
    
    print("Goodbye!")

# ============================================================================
# CLI ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # This allows running: python app.py
    # Which starts the dev server
    app.run(debug=True)
