# Axiom Framework: Core Architecture

## Framework Identity

**Name:** Axiom  
**Tagline:** AI-native full-stack framework with compiler-driven code generation  
**Core Premise:** Developers declare intent in Python DSL → Compiler generates production React + FastAPI + Agent runtime

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPER LAYER                              │
│                 (Python DSL: app.py)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   AXIOM COMPILER                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  AST Parser → IR Builder → Validator → Code Generator   │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────┬─────────────────────────┬───────────────────────┘
                │                         │
       ┌────────▼────────┐       ┌───────▼────────┐
       │  REACT CODEGEN  │       │ FASTAPI CODEGEN│
       │  (TypeScript)   │       │  (Python/ASGI) │
       └────────┬────────┘       └───────┬────────┘
                │                        │
                └────────┬───────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   AGENT RUNTIME CORE                            │
│  ┌────────────────┬──────────────┬─────────────────────────┐   │
│  │  Reasoning     │  Memory      │  MCP Tool Registry      │   │
│  │  Loop Engine   │  Engine      │  (Server/Client)        │   │
│  └────────────────┴──────────────┴─────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Multi-Agent Orchestrator (Context Isolation)          │    │
│  └────────────────────────────────────────────────────────┘    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              INFRASTRUCTURE LAYER                               │
│  ┌──────────────┬──────────────┬─────────────────────────┐     │
│  │  pgvector    │  Neo4j       │  Redis                  │     │
│  │  (vectors)   │  (graph)     │  (cache)                │     │
│  └──────────────┴──────────────┴─────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Python DSL Layer
- Decorators for agents, views, workflows
- Type-safe configuration
- Valid Python syntax (no custom parser needed)

### 2. Compiler Pipeline
- **AST Parser:** Python code → Abstract Syntax Tree
- **IR Builder:** AST → Axiom Intermediate Representation
- **Validator:** Type checking, constraint validation
- **Code Generators:** IR → React/FastAPI/Docker/K8s

### 3. Agent Runtime
- **Reasoning Loop:** LLM-driven decision making with tool orchestration
- **Memory Engine:** Hybrid vector + graph + cache storage
- **MCP Integration:** Tool execution via Model Context Protocol
- **Orchestrator:** Multi-agent coordination with context isolation

### 4. Generated Artifacts
- **Frontend:** React + TypeScript components with Tailwind
- **Backend:** FastAPI routes + agent endpoints
- **Infrastructure:** Docker images, K8s manifests, configs

---

## Design Principles

### 1. Declaration Over Implementation
Developers declare what they want, not how to build it.

### 2. Compilation Guarantees
Catch errors at compile time, not runtime. Type safety throughout.

### 3. AI as Native Primitive
Agents and reasoning are language constructs, not library calls.

### 4. Zero Lock-in
Based on open standards: MCP, OpenTelemetry, standard databases.

### 5. Production-First
Every generated artifact is production-ready, secure, and scalable.

---

## Execution Flow

```
Developer writes app.py (Python DSL)
        ↓
axiom build (compile)
        ↓
Generates dist/ folder:
  ├── frontend/ (React + TypeScript)
  ├── backend/ (FastAPI + Agent runtime)
  ├── docker/ (Dockerfiles)
  └── kubernetes/ (K8s manifests)
        ↓
axiom dev (local development)
  - Hot reload for both frontend & backend
  - Local MCP servers
  - Docker Compose for databases
        ↓
axiom deploy (production)
  - Build Docker images
  - Push to registry
  - Deploy to Kubernetes
  - Initialize databases
```

---

## Technology Stack

**Frontend:**
- React 18+
- TypeScript
- Tailwind CSS
- Vite (build tool)
- WebSocket for real-time updates

**Backend:**
- FastAPI (async Python)
- Uvicorn (ASGI server)
- Pydantic (validation)

**Agent Runtime:**
- Anthropic Claude (default LLM)
- OpenAI SDK (multi-provider)
- MCP Protocol (tool integration)

**Memory:**
- PostgreSQL + pgvector (vector search)
- Neo4j (graph relationships)
- Redis (caching)

**Infrastructure:**
- Kubernetes (orchestration)
- Docker (containerization)
- OpenTelemetry (observability)

---

## Key Differentiators

### vs Django/Flask
- Generates frontend automatically
- AI agents as first-class citizens
- Compiler-driven vs runtime framework

### vs Next.js
- Python-first (not JavaScript)
- AI runtime built-in
- Generates backend automatically

### vs LangChain
- Full-stack framework (not just library)
- Type-safe compilation
- Production-ready out of box

### vs CrewAI
- Includes UI layer
- Declarative workflows
- Complete application framework

---

## Performance Targets

- **API Latency (p95):** <50ms for simple requests
- **Agent Execution:** <2s with tool calls
- **Memory Query:** <100ms
- **Throughput:** 10k+ RPS per pod
- **Concurrent Users:** 100k+ (horizontally scaled)
- **WebSocket Connections:** 10k+ per pod

---

## Security Model

1. **Authentication:** Provider-agnostic (Clerk, Auth0, custom)
2. **Authorization:** RBAC with resource-level permissions
3. **Context Isolation:** Each agent runs in isolated context
4. **Rate Limiting:** Per-user and per-agent limits
5. **Encryption:** At-rest and in-transit
6. **Audit Logging:** Every operation logged

---

## Development Workflow

```bash
# Create new project
axiom new my-app

# Start development server
cd my-app
axiom dev

# Build for production
axiom build --prod

# Deploy to Kubernetes
axiom deploy --cluster production

# Run tests
axiom test

# View logs
axiom logs --agent research_agent
```

---

## Project Structure

```
my-app/
├── app.py                 # Main application (DSL)
├── agents/               # Agent definitions
│   ├── research.py
│   └── synthesis.py
├── views/                # UI views
│   └── dashboard.py
├── mcp-servers/          # Custom MCP servers
│   └── internal-api/
├── axiom.config.json     # Framework configuration
├── requirements.txt
└── dist/                 # Generated code (git-ignored)
    ├── frontend/
    ├── backend/
    └── kubernetes/
```

---

## Roadmap Summary

**Year 1 (2026):** Core framework, cloud launch, 1k users  
**Year 2 (2027):** Enterprise features, 10k apps deployed  
**Year 3 (2028):** Platform maturity, 1M+ developers

---

## Open Source Model

- **License:** Apache 2.0
- **Governance:** Technical Steering Committee
- **Funding:** Foundation grants + cloud service revenue
- **Community:** Monthly calls, annual conference

---

## Success Metrics

- **Developer Adoption:** 10k developers in year 1
- **Applications Deployed:** 1k production apps in year 1
- **Community Contributions:** 100+ merged PRs per month
- **Enterprise Customers:** 10+ Fortune 500 companies by year 2
- **Marketplace:** 100+ plugins by year 2
