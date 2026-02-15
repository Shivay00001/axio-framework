# ⚡ Axio Framework

**The AI-Native Full-Stack Engine**

[![PyPI version](https://img.shields.io/pypi/v/axio-framework.svg)](https://pypi.org/project/axio-framework/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![GitHub](https://img.shields.io/github/stars/Shivay00001/axio-framework?style=social)](https://github.com/Shivay00001/axio-framework)

---

**Axio** is a high-performance, AI-native framework designed for the future of software development. It enables developers to build complex, full-stack applications by declaring intent in a simple Python DSL. The Axio compiler then transforms these declarations into production-ready **React** frontends, **FastAPI** backends, and isolated **Agent Runtimes**.

## 🚀 Key Differentiators

* **Declaration Over Implementation**: Stop writing boilerplate. Define agents, views, and workflows; Axio handles the rest.
* **AI as a First-Class Citizen**: Reasoning loops, tool orchestration, and memory are built directly into the language constructs.
* **Multi-Agent Orchestrator**: Native support for complex, coordinated multi-agent workflows with context isolation.
* **Hybrid Memory Engine**: Seamless integration of Vector (Semantic), Graph (Relationship), and Cache storage.
* **MCP Native**: Built-in support for the Model Context Protocol to easily connect agents to any tool or data source.

## 🛠️ Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 18+, TypeScript, Tailwind CSS, Vite |
| **Backend** | FastAPI, Uvicorn, Pydantic |
| **Agents** | Claude-3.5-Sonnet (Default), OpenAI, Multi-Model Logic |
| **Memory** | pgvector (PostgreSQL), Neo4j (Graph), Redis (Cache) |
| **Infrastructure** | Docker, Kubernetes, OpenTelemetry |

## 📦 Installation

```bash
pip install axio-framework
```

## 🏗️ Quick Start

### 1. Initialize Project

```bash
axio new my-smart-app
cd my-smart-app
```

### 2. Define an Agent (app.py)

```python
@app.agent(name="researcher", model="claude-sonnet-4")
class ResearchAgent:
    async def analyze(self, query: str):
        return await self.reason(objective=f"Analyze {query}")
```

### 3. Run Development Server

```bash
axio dev
```

## 📜 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">Built with ❤️ for the AI Engineer Era</p>
