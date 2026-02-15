"""
Axiom CLI Tool

Command-line interface for creating, building, and deploying Axiom applications

Commands:
- axiom new <project>     Create new project
- axiom dev              Start development server
- axiom build            Compile application
- axiom deploy           Deploy to production
- axiom test             Run tests
- axiom logs             View logs
"""

import click
import asyncio
from pathlib import Path
import subprocess
import sys
from typing import Optional
import yaml


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Axiom: AI-Native Full-Stack Framework"""
    pass


# ============================================================================
# PROJECT CREATION
# ============================================================================

@cli.command()
@click.argument('name')
@click.option('--template', default='basic', help='Project template')
@click.option('--dir', default='.', help='Target directory')
def new(name: str, template: str, dir: str):
    """Create a new Axiom project"""
    
    click.echo(f"Creating new Axiom project: {name}")
    
    # Create project directory
    project_dir = Path(dir) / name
    if project_dir.exists():
        click.echo(f"Error: Directory {project_dir} already exists", err=True)
        sys.exit(1)
    
    project_dir.mkdir(parents=True)
    
    # Create project structure
    _create_project_structure(project_dir, name, template)
    
    click.echo(f"\n✓ Project created at {project_dir}")
    click.echo(f"\nNext steps:")
    click.echo(f"  cd {name}")
    click.echo(f"  axiom dev")


def _create_project_structure(project_dir: Path, name: str, template: str):
    """Create project files and directories"""
    
    # Create directories
    (project_dir / "agents").mkdir()
    (project_dir / "views").mkdir()
    (project_dir / "mcp-servers").mkdir()
    
    # Create main app file
    app_content = _get_template_app(name, template)
    (project_dir / "app.py").write_text(app_content)
    
    # Create requirements.txt
    (project_dir / "requirements.txt").write_text("""axiom-framework>=1.0.0
anthropic>=0.20.0
fastapi>=0.110.0
uvicorn>=0.28.0
asyncpg>=0.29.0
neo4j>=5.18.0
redis>=5.0.0
""")
    
    # Create axiom.config.json
    config = {
        "name": name,
        "version": "0.1.0",
        "python_version": "3.11",
        "memory": {
            "backend": "hybrid",
            "vector_dims": 1536
        },
        "security": {
            "auth_provider": "clerk",
            "rbac_enabled": True
        }
    }
    (project_dir / "axiom.config.json").write_text(
        yaml.dump(config, indent=2)
    )
    
    # Create .gitignore
    (project_dir / ".gitignore").write_text("""__pycache__/
*.py[cod]
*$py.class
.Python
dist/
.env
.venv
env/
venv/
node_modules/
""")
    
    # Create README
    (project_dir / "README.md").write_text(f"""# {name}

Axiom AI-native application

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Start development server
axiom dev

# Build for production
axiom build --prod

# Deploy
axiom deploy
```
""")


def _get_template_app(name: str, template: str) -> str:
    """Get app.py template content"""
    
    if template == "basic":
        return f'''"""
{name} - Axiom Application
"""

from axiom import App, Agent, View
from axiom.ui import Container, Card, Markdown

app = App(
    name="{name}",
    version="0.1.0",
    description="My Axiom application"
)

@app.view(route="/", auth_required=False)
class HomePage(View):
    """Home page"""
    
    def layout(self):
        return Container([
            Card([
                Markdown("""
                # Welcome to {name}
                
                Built with Axiom Framework
                """)
            ])
        ])

if __name__ == "__main__":
    app.run(debug=True)
'''
    
    return ""


# ============================================================================
# DEVELOPMENT SERVER
# ============================================================================

@cli.command()
@click.option('--host', default='localhost', help='Host to bind')
@click.option('--port', default=8000, help='Port to bind')
@click.option('--reload/--no-reload', default=True, help='Auto-reload on changes')
def dev(host: str, port: int, reload: bool):
    """Start development server"""
    
    click.echo("Starting Axiom development server...")
    
    # Check for app.py
    if not Path("app.py").exists():
        click.echo("Error: app.py not found. Run 'axiom new <project>' first.", err=True)
        sys.exit(1)
    
    # Start infrastructure (Docker Compose)
    click.echo("\n1. Starting infrastructure...")
    _start_infrastructure()
    
    # Compile application
    click.echo("\n2. Compiling application...")
    compile_result = _compile_app(prod=False)
    if not compile_result:
        sys.exit(1)
    
    # Start backend server
    click.echo("\n3. Starting backend server...")
    backend_process = _start_backend(host, port, reload)
    
    # Start frontend dev server
    click.echo("\n4. Starting frontend dev server...")
    frontend_process = _start_frontend()
    
    click.echo(f"\n✓ Development server running")
    click.echo(f"  - Frontend: http://localhost:3000")
    click.echo(f"  - Backend:  http://{host}:{port}")
    click.echo(f"  - API Docs: http://{host}:{port}/docs")
    click.echo(f"\nPress Ctrl+C to stop")
    
    try:
        # Wait for processes
        backend_process.wait()
    except KeyboardInterrupt:
        click.echo("\n\nStopping servers...")
        backend_process.terminate()
        frontend_process.terminate()


def _start_infrastructure():
    """Start Docker Compose services"""
    
    # Check if docker-compose.yml exists
    if not Path("docker-compose.yml").exists():
        # Create default docker-compose.yml
        compose_content = """version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: axiom
      POSTGRES_USER: axiom
      POSTGRES_PASSWORD: axiom
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/axiom123
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  neo4j_data:
  redis_data:
"""
        Path("docker-compose.yml").write_text(compose_content)
    
    # Start services
    subprocess.run(["docker-compose", "up", "-d"], check=True)


def _compile_app(prod: bool = False) -> bool:
    """Compile Axiom application"""
    
    from compiler import AxiomCompiler
    
    compiler = AxiomCompiler(project_root=Path.cwd())
    result = compiler.compile(entrypoint=Path("app.py"))
    
    if not result.success:
        click.echo("Compilation failed:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        return False
    
    click.echo(f"  - {len(result.ir.agents)} agents")
    click.echo(f"  - {len(result.ir.views)} views")
    click.echo(f"  - {len(result.ir.api_routes)} API routes")
    
    return True


def _start_backend(host: str, port: int, reload: bool):
    """Start FastAPI backend"""
    
    # Start uvicorn
    cmd = [
        "uvicorn",
        "dist.backend.main:app",
        "--host", host,
        "--port", str(port)
    ]
    
    if reload:
        cmd.extend(["--reload", "--reload-dir", "dist/backend"])
    
    return subprocess.Popen(cmd)


def _start_frontend():
    """Start Vite frontend dev server"""
    
    frontend_dir = Path("dist/frontend")
    
    # Install dependencies if needed
    if not (frontend_dir / "node_modules").exists():
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
    
    # Start vite
    return subprocess.Popen(["npm", "run", "dev"], cwd=frontend_dir)


# ============================================================================
# BUILD COMMAND
# ============================================================================

@cli.command()
@click.option('--prod/--dev', default=True, help='Production or development build')
@click.option('--output', default='dist', help='Output directory')
def build(prod: bool, output: str):
    """Compile application to production code"""
    
    click.echo("Building Axiom application...")
    
    from compiler import AxiomCompiler
    from react_generator import ReactGenerator
    from backend_generator import BackendGenerator
    
    # Compile
    click.echo("\n1. Compiling...")
    compiler = AxiomCompiler(project_root=Path.cwd())
    result = compiler.compile(entrypoint=Path("app.py"))
    
    if not result.success:
        click.echo("Build failed:", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)
    
    # Generate React frontend
    click.echo("\n2. Generating frontend...")
    react_gen = ReactGenerator()
    frontend = react_gen.generate(result.ir)
    
    # Write frontend files
    frontend_dir = Path(output) / "frontend"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    
    for component in frontend.components:
        path = frontend_dir / component.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(component.content)
    
    # Write package.json
    (frontend_dir / "package.json").write_text(
        yaml.dump(frontend.package_json, indent=2)
    )
    
    # Generate FastAPI backend
    click.echo("\n3. Generating backend...")
    backend_gen = BackendGenerator()
    backend = backend_gen.generate(result.ir)
    
    # Write backend files
    backend_dir = Path(output) / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    
    (backend_dir / backend.main.path).write_text(backend.main.content)
    (backend_dir / backend.models.path).write_text(backend.models.content)
    (backend_dir / "requirements.txt").write_text(backend.requirements)
    
    # Generate Docker images
    click.echo("\n4. Generating Docker configuration...")
    _generate_docker_config(Path(output), result.ir)
    
    # Generate Kubernetes manifests
    click.echo("\n5. Generating Kubernetes manifests...")
    _generate_k8s_config(Path(output), result.ir)
    
    if prod:
        # Build production frontend
        click.echo("\n6. Building production frontend...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=frontend_dir,
            check=True
        )
    
    click.echo(f"\n✓ Build complete: {output}/")


def _generate_docker_config(output_dir: Path, ir: 'AxiomIR'):
    """Generate Dockerfile"""
    
    backend_dockerfile = f"""FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dist/backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
    
    (output_dir / "docker" / "backend.Dockerfile").parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "docker" / "backend.Dockerfile").write_text(backend_dockerfile)
    
    frontend_dockerfile = """FROM node:20-alpine as builder

WORKDIR /app

COPY dist/frontend/package*.json ./
RUN npm ci

COPY dist/frontend .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
"""
    
    (output_dir / "docker" / "frontend.Dockerfile").write_text(frontend_dockerfile)


def _generate_k8s_config(output_dir: Path, ir: 'AxiomIR'):
    """Generate Kubernetes manifests"""
    
    k8s_dir = output_dir / "kubernetes"
    k8s_dir.mkdir(parents=True, exist_ok=True)
    
    # Backend deployment
    backend_deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": f"{ir.app_metadata.name}-backend"},
        "spec": {
            "replicas": 3,
            "selector": {
                "matchLabels": {"app": f"{ir.app_metadata.name}-backend"}
            },
            "template": {
                "metadata": {
                    "labels": {"app": f"{ir.app_metadata.name}-backend"}
                },
                "spec": {
                    "containers": [{
                        "name": "backend",
                        "image": f"{ir.app_metadata.name}-backend:latest",
                        "ports": [{"containerPort": 8000}],
                        "resources": {
                            "requests": {"memory": "1Gi", "cpu": "500m"},
                            "limits": {"memory": "2Gi", "cpu": "1000m"}
                        }
                    }]
                }
            }
        }
    }
    
    (k8s_dir / "backend-deployment.yaml").write_text(
        yaml.dump(backend_deployment, indent=2)
    )


# ============================================================================
# DEPLOYMENT
# ============================================================================

@cli.command()
@click.option('--cluster', default='production', help='Kubernetes cluster')
@click.option('--namespace', default='default', help='Kubernetes namespace')
def deploy(cluster: str, namespace: str):
    """Deploy application to Kubernetes"""
    
    click.echo(f"Deploying to {cluster}...")
    
    # Build first
    click.echo("\n1. Building application...")
    ctx = click.get_current_context()
    ctx.invoke(build, prod=True)
    
    # Build Docker images
    click.echo("\n2. Building Docker images...")
    subprocess.run([
        "docker", "build",
        "-f", "dist/docker/backend.Dockerfile",
        "-t", "axiom-backend:latest",
        "."
    ], check=True)
    
    subprocess.run([
        "docker", "build",
        "-f", "dist/docker/frontend.Dockerfile",
        "-t", "axiom-frontend:latest",
        "."
    ], check=True)
    
    # Push images
    click.echo("\n3. Pushing images...")
    # (Would push to container registry)
    
    # Apply Kubernetes manifests
    click.echo("\n4. Applying Kubernetes manifests...")
    subprocess.run([
        "kubectl", "apply",
        "-f", "dist/kubernetes/",
        "--namespace", namespace
    ], check=True)
    
    click.echo("\n✓ Deployment complete")


# ============================================================================
# TESTING
# ============================================================================

@cli.command()
@click.option('--coverage/--no-coverage', default=False, help='Generate coverage report')
def test(coverage: bool):
    """Run tests"""
    
    click.echo("Running tests...")
    
    # Backend tests
    click.echo("\n1. Backend tests:")
    cmd = ["pytest", "tests/"]
    if coverage:
        cmd.extend(["--cov=dist/backend", "--cov-report=html"])
    
    subprocess.run(cmd, check=True)
    
    # Frontend tests
    click.echo("\n2. Frontend tests:")
    subprocess.run(
        ["npm", "test"],
        cwd="dist/frontend",
        check=True
    )
    
    click.echo("\n✓ All tests passed")


# ============================================================================
# LOGS
# ============================================================================

@cli.command()
@click.option('--agent', help='Filter by agent name')
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--tail', default=100, help='Number of lines to show')
def logs(agent: Optional[str], follow: bool, tail: int):
    """View application logs"""
    
    if agent:
        click.echo(f"Viewing logs for agent: {agent}")
    else:
        click.echo("Viewing all logs")
    
    # In production, would query logging backend (Loki, CloudWatch, etc.)
    # For now, show kubectl logs
    
    cmd = ["kubectl", "logs", "-l", "app=axiom-backend"]
    
    if follow:
        cmd.append("-f")
    
    cmd.extend(["--tail", str(tail)])
    
    subprocess.run(cmd)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    cli()
