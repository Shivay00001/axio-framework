# Axio Framework

AI-native full-stack framework with compiler-driven code generation.

## Overview

Axio allows developers to declare intent in Python DSL, which the compiler then transforms into a production-ready React + FastAPI application with an integrated AI agent runtime.

## Core Features

- **Declaration Over Implementation**: Define agents, views, and workflows in simple Python.
- **AI-Native**: Agents and reasoning loops are first-class citizens.
- **Compiler-Driven**: Generates typed TypeScript (React) and Python (FastAPI).
- **Hybrid Memory**: Built-in support for Vector, Graph, and Cache storage.
- **MCP Integration**: First-class support for Model Context Protocol tools.

## Installation

```bash
pip install axio-framework
```

## Quick Start

1. Create a new project:

   ```bash
   axio new my-app
   ```

2. Start development server:

   ```bash
   cd my-app
   axio dev
   ```

3. Build for production:

   ```bash
   axio build --prod
   ```

## Documentation

For detailed architectural overview, see `README_ADVANCED.md` or our online documentation.

## License

Apache 2.0
