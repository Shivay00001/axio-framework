"""
Axiom Compiler: Python DSL → Production Code

Multi-stage compilation pipeline:
1. Parse Python AST
2. Build Intermediate Representation (IR)
3. Validate IR (type checking, constraints)
4. Generate code for multiple targets (React, FastAPI, Docker, K8s)
"""

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from enum import Enum


# ============================================================================
# INTERMEDIATE REPRESENTATION (IR)
# ============================================================================

class ModelProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CUSTOM = "custom"

@dataclass
class TypeInfo:
    """Type information extracted from Python type hints"""
    name: str
    module: Optional[str] = None
    is_optional: bool = False
    is_list: bool = False
    is_dict: bool = False
    generic_args: list['TypeInfo'] = field(default_factory=list)

@dataclass
class Parameter:
    name: str
    type_info: TypeInfo
    default: Any = None
    required: bool = True

@dataclass
class ToolSpec:
    """MCP tool specification"""
    server: str
    name: str
    qualified_name: str  # e.g., "github.search_repos"

@dataclass
class MemorySchemaSpec:
    """Memory schema specification"""
    name: str
    fields: dict[str, TypeInfo]
    vector_field: Optional[str] = None
    vector_dims: Optional[int] = None
    graph_config: Optional[dict] = None

@dataclass
class ReasoningConfig:
    max_iterations: int = 10
    reflection_enabled: bool = False
    tool_parallelism: bool = True
    temperature: float = 0.1

@dataclass
class MethodSpec:
    """Agent method specification"""
    name: str
    parameters: list[Parameter]
    return_type: TypeInfo
    docstring: str
    body: ast.AST  # Original AST for code generation
    has_reasoning: bool = False  # Does it call self.reason()?
    
@dataclass
class AgentSpec:
    """Agent specification in IR"""
    name: str
    model: str
    memory_schema: Optional[MemorySchemaSpec]
    tools: list[ToolSpec]
    methods: dict[str, MethodSpec]
    reasoning_config: ReasoningConfig
    docstring: str

@dataclass
class StateField:
    name: str
    type_info: TypeInfo
    default: Any = None

@dataclass
class ActionSpec:
    """View action specification"""
    name: str
    parameters: list[Parameter]
    body: ast.AST
    debounce: Optional[int] = None
    throttle: Optional[int] = None

@dataclass
class LayoutNode:
    """UI layout tree node"""
    component: str
    props: dict[str, Any]
    children: list['LayoutNode'] = field(default_factory=list)
    
@dataclass
class ViewSpec:
    """View specification in IR"""
    name: str
    route: str
    state: dict[str, StateField]
    initial_state: dict[str, Any]
    layout: LayoutNode
    actions: list[ActionSpec]
    auth_required: bool
    lifecycle_hooks: dict[str, ast.AST] = field(default_factory=dict)

@dataclass
class RouteSpec:
    """API route specification"""
    path: str
    methods: list[str]
    handler_name: str
    parameters: list[Parameter]
    body: ast.AST
    auth_required: bool
    permissions: list[str]

@dataclass
class WorkflowStep:
    name: str
    parallel: bool
    agents: dict[str, dict]  # agent_name -> task config

@dataclass
class WorkflowSpec:
    name: str
    steps: list[WorkflowStep]

@dataclass
class AppMetadata:
    name: str
    version: str
    description: str

@dataclass
class AxiomIR:
    """Complete Intermediate Representation"""
    app_metadata: AppMetadata
    agents: dict[str, AgentSpec]
    views: dict[str, ViewSpec]
    api_routes: list[RouteSpec]
    workflows: dict[str, WorkflowSpec]
    memory_schemas: dict[str, MemorySchemaSpec]
    mcp_servers: dict[str, dict]
    config: dict[str, Any]


# ============================================================================
# AST PARSER & IR BUILDER
# ============================================================================

class IRBuilder(ast.NodeVisitor):
    """
    Transforms Python AST into Axiom IR
    
    Walks through the AST and extracts:
    - App configuration
    - Agent definitions
    - View definitions
    - API routes
    - Workflows
    - Memory schemas
    """
    
    def __init__(self):
        self.ir = AxiomIR(
            app_metadata=AppMetadata(name="", version="", description=""),
            agents={},
            views={},
            api_routes=[],
            workflows={},
            memory_schemas={},
            mcp_servers={},
            config={}
        )
        self.current_class: Optional[str] = None
        self.app_decorators: dict[str, dict] = {}
    
    def build(self, tree: ast.AST) -> AxiomIR:
        """Build IR from AST"""
        self.visit(tree)
        return self.ir
    
    def visit_Call(self, node: ast.Call):
        """Visit function calls - look for App() instantiation"""
        if isinstance(node.func, ast.Name) and node.func.id == "App":
            self._extract_app_config(node)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definitions"""
        self.current_class = node.name
        
        # Check decorators to determine what kind of class this is
        decorators = self._get_decorators(node)
        
        if "agent" in decorators:
            self._build_agent_spec(node, decorators["agent"])
        elif "memory_schema" in decorators:
            self._build_memory_schema(node)
        elif self._has_base_class(node, "View"):
            self._build_view_spec(node)
        elif self._has_base_class(node, "Workflow"):
            self._build_workflow_spec(node)
        
        self.current_class = None
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions"""
        decorators = self._get_decorators(node)
        
        if "api" in decorators:
            self._build_route_spec(node, decorators["api"])
        
        self.generic_visit(node)
    
    def _extract_app_config(self, node: ast.Call):
        """Extract App() configuration"""
        for keyword in node.keywords:
            if keyword.arg == "name":
                self.ir.app_metadata.name = ast.literal_eval(keyword.value)
            elif keyword.arg == "version":
                self.ir.app_metadata.version = ast.literal_eval(keyword.value)
            elif keyword.arg == "description":
                self.ir.app_metadata.description = ast.literal_eval(keyword.value)
            elif keyword.arg == "config":
                self.ir.config = ast.literal_eval(keyword.value)
    
    def _build_agent_spec(self, node: ast.ClassDef, decorator_args: dict):
        """Build AgentSpec from class definition"""
        
        # Extract agent configuration from decorator
        name = decorator_args.get("name", node.name.lower())
        model = decorator_args.get("model", "claude-sonnet-4")
        memory_schema_name = decorator_args.get("memory")
        tools_list = decorator_args.get("tools", [])
        reasoning_config = decorator_args.get("reasoning", {})
        
        # Parse tools
        tools = []
        for tool in tools_list:
            if isinstance(tool, dict):
                tools.append(ToolSpec(
                    server=tool["server"],
                    name=tool["name"],
                    qualified_name=f"{tool['server']}.{tool['name']}"
                ))
        
        # Extract methods
        methods = {}
        for item in node.body:
            if isinstance(item, ast.AsyncFunctionDef):
                method_spec = self._build_method_spec(item)
                methods[item.name] = method_spec
        
        # Get memory schema if specified
        memory_schema = None
        if memory_schema_name and isinstance(memory_schema_name, str):
            memory_schema = self.ir.memory_schemas.get(memory_schema_name)
        
        agent_spec = AgentSpec(
            name=name,
            model=model,
            memory_schema=memory_schema,
            tools=tools,
            methods=methods,
            reasoning_config=ReasoningConfig(**reasoning_config),
            docstring=ast.get_docstring(node) or ""
        )
        
        self.ir.agents[name] = agent_spec
    
    def _build_method_spec(self, node: ast.AsyncFunctionDef) -> MethodSpec:
        """Build MethodSpec from async function definition"""
        
        # Extract parameters
        parameters = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            
            param = Parameter(
                name=arg.arg,
                type_info=self._parse_type_annotation(arg.annotation),
                required=True
            )
            parameters.append(param)
        
        # Extract return type
        return_type = self._parse_type_annotation(node.returns)
        
        # Check if method uses self.reason()
        has_reasoning = self._check_for_reasoning_call(node)
        
        return MethodSpec(
            name=node.name,
            parameters=parameters,
            return_type=return_type,
            docstring=ast.get_docstring(node) or "",
            body=node,
            has_reasoning=has_reasoning
        )
    
    def _build_view_spec(self, node: ast.ClassDef):
        """Build ViewSpec from View class"""
        
        # Find view decorator or extract from base class usage
        route = "/"
        auth_required = False
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "view":
                        for kw in decorator.keywords:
                            if kw.arg == "route":
                                route = ast.literal_eval(kw.value)
                            elif kw.arg == "auth_required":
                                auth_required = ast.literal_eval(kw.value)
        
        # Extract state definition
        state = {}
        initial_state = {}
        
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "state":
                            state = self._parse_state_definition(item.value)
                        elif target.id == "initial_state":
                            initial_state = ast.literal_eval(item.value)
        
        # Extract layout method
        layout = None
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "layout":
                layout = self._parse_layout(item)
        
        # Extract actions
        actions = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = self._get_decorators(item)
                if "Action" in decorators:
                    action = self._build_action_spec(item, decorators["Action"])
                    actions.append(action)
        
        view_spec = ViewSpec(
            name=node.name,
            route=route,
            state=state,
            initial_state=initial_state,
            layout=layout,
            actions=actions,
            auth_required=auth_required
        )
        
        self.ir.views[node.name] = view_spec
    
    def _build_memory_schema(self, node: ast.ClassDef):
        """Build MemorySchemaSpec from class definition"""
        
        fields = {}
        vector_field = None
        vector_dims = None
        graph_config = None
        
        for item in node.body:
            if isinstance(item, ast.AnnAssign):
                field_name = item.target.id
                type_info = self._parse_type_annotation(item.annotation)
                
                # Check for special types (Vector, Graph)
                if isinstance(item.annotation, ast.Call):
                    if isinstance(item.annotation.func, ast.Name):
                        if item.annotation.func.id == "Vector":
                            vector_field = field_name
                            # Extract dims
                            for kw in item.annotation.keywords:
                                if kw.arg == "dims":
                                    vector_dims = ast.literal_eval(kw.value)
                        elif item.annotation.func.id == "Graph":
                            graph_config = self._parse_graph_config(item.annotation)
                
                fields[field_name] = type_info
        
        schema = MemorySchemaSpec(
            name=node.name,
            fields=fields,
            vector_field=vector_field,
            vector_dims=vector_dims,
            graph_config=graph_config
        )
        
        self.ir.memory_schemas[node.name] = schema
    
    def _build_route_spec(self, node: ast.FunctionDef, decorator_args: dict):
        """Build RouteSpec from API route function"""
        
        path = decorator_args.get("path", "/")
        methods = decorator_args.get("methods", ["GET"])
        
        # Extract parameters
        parameters = []
        for arg in node.args.args:
            if arg.arg == "ctx":
                continue
            param = Parameter(
                name=arg.arg,
                type_info=self._parse_type_annotation(arg.annotation),
                required=True
            )
            parameters.append(param)
        
        # Check for permission decorators
        permissions = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    if decorator.func.id == "RequirePermission":
                        perm = ast.literal_eval(decorator.args[0])
                        permissions.append(perm)
        
        route = RouteSpec(
            path=path,
            methods=methods,
            handler_name=node.name,
            parameters=parameters,
            body=node,
            auth_required=len(permissions) > 0,
            permissions=permissions
        )
        
        self.ir.api_routes.append(route)
    
    def _parse_type_annotation(self, annotation: Optional[ast.AST]) -> TypeInfo:
        """Parse Python type annotation into TypeInfo"""
        
        if annotation is None:
            return TypeInfo(name="Any")
        
        if isinstance(annotation, ast.Name):
            return TypeInfo(name=annotation.id)
        
        if isinstance(annotation, ast.Subscript):
            # Handle Generic[T] types
            if isinstance(annotation.value, ast.Name):
                base_type = annotation.value.id
                
                # Handle Optional[T]
                if base_type == "Optional":
                    inner = self._parse_type_annotation(annotation.slice)
                    inner.is_optional = True
                    return inner
                
                # Handle list[T]
                if base_type == "list":
                    inner = self._parse_type_annotation(annotation.slice)
                    return TypeInfo(
                        name="list",
                        is_list=True,
                        generic_args=[inner]
                    )
                
                # Handle dict[K, V]
                if base_type == "dict":
                    return TypeInfo(name="dict", is_dict=True)
        
        return TypeInfo(name="Unknown")
    
    def _check_for_reasoning_call(self, node: ast.AsyncFunctionDef) -> bool:
        """Check if function calls self.reason()"""
        
        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                if isinstance(child.value, ast.Call):
                    if isinstance(child.value.func, ast.Attribute):
                        if child.value.func.attr == "reason":
                            return True
        return False
    
    def _get_decorators(self, node: ast.AST) -> dict[str, dict]:
        """Extract decorators and their arguments"""
        
        decorators = {}
        
        if not hasattr(node, 'decorator_list'):
            return decorators
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators[decorator.id] = {}
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    name = decorator.func.attr
                    args = {}
                    for kw in decorator.keywords:
                        try:
                            args[kw.arg] = ast.literal_eval(kw.value)
                        except:
                            args[kw.arg] = kw.value
                    decorators[name] = args
                elif isinstance(decorator.func, ast.Name):
                    name = decorator.func.id
                    args = {}
                    for kw in decorator.keywords:
                        try:
                            args[kw.arg] = ast.literal_eval(kw.value)
                        except:
                            args[kw.arg] = kw.value
                    decorators[name] = args
        
        return decorators
    
    def _has_base_class(self, node: ast.ClassDef, base_name: str) -> bool:
        """Check if class inherits from base_name"""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == base_name:
                return True
        return False
    
    def _parse_layout(self, node: ast.FunctionDef) -> LayoutNode:
        """Parse layout method and build layout tree"""
        # This would be a complex parser for the UI DSL
        # For now, return a placeholder
        return LayoutNode(component="Container", props={}, children=[])
    
    def _parse_state_definition(self, node: ast.AST) -> dict[str, StateField]:
        """Parse state definition"""
        # Simplified implementation
        return {}
    
    def _build_action_spec(self, node: ast.AST, decorator_args: dict) -> ActionSpec:
        """Build ActionSpec from decorated method"""
        return ActionSpec(
            name=node.name,
            parameters=[],
            body=node,
            debounce=decorator_args.get("debounce"),
            throttle=decorator_args.get("throttle")
        )
    
    def _parse_graph_config(self, node: ast.Call) -> dict:
        """Parse Graph() configuration"""
        config = {}
        for kw in node.keywords:
            config[kw.arg] = ast.literal_eval(kw.value)
        return config


# ============================================================================
# COMPILER PIPELINE
# ============================================================================

@dataclass
class CompilationResult:
    ir: AxiomIR
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

class AxiomCompiler:
    """
    Main compiler class
    
    Orchestrates the compilation pipeline:
    1. Parse Python code → AST
    2. Build IR from AST
    3. Validate IR
    4. Generate code for each target
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.ir_builder = IRBuilder()
    
    def compile(self, entrypoint: Path = Path("app.py")) -> CompilationResult:
        """Compile Axiom application"""
        
        print(f"Compiling {entrypoint}...")
        
        # Stage 1: Parse Python to AST
        source = (self.project_root / entrypoint).read_text()
        try:
            python_ast = ast.parse(source, filename=str(entrypoint))
        except SyntaxError as e:
            return CompilationResult(
                ir=None,
                success=False,
                errors=[f"Syntax error: {e}"]
            )
        
        # Stage 2: Build IR
        print("Building intermediate representation...")
        ir = self.ir_builder.build(python_ast)
        
        # Stage 3: Validate IR
        print("Validating...")
        validation_errors = self._validate_ir(ir)
        
        if validation_errors:
            return CompilationResult(
                ir=ir,
                success=False,
                errors=validation_errors
            )
        
        print("✓ Compilation successful")
        
        return CompilationResult(
            ir=ir,
            success=True
        )
    
    def _validate_ir(self, ir: AxiomIR) -> list[str]:
        """Validate IR for correctness"""
        
        errors = []
        
        # Check that app has a name
        if not ir.app_metadata.name:
            errors.append("App must have a name")
        
        # Validate agents
        for agent_name, agent in ir.agents.items():
            # Check that methods exist
            if not agent.methods:
                errors.append(f"Agent {agent_name} has no methods")
            
            # Check tool references
            for tool in agent.tools:
                if tool.server not in ir.mcp_servers:
                    errors.append(
                        f"Agent {agent_name} references unknown MCP server: {tool.server}"
                    )
        
        # Validate views
        for view_name, view in ir.views.items():
            if not view.layout:
                errors.append(f"View {view_name} has no layout")
        
        return errors


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    compiler = AxiomCompiler(project_root=Path.cwd())
    result = compiler.compile(entrypoint=Path("app.py"))
    
    if result.success:
        print(f"\n✓ Compiled successfully")
        print(f"  - {len(result.ir.agents)} agents")
        print(f"  - {len(result.ir.views)} views")
        print(f"  - {len(result.ir.api_routes)} API routes")
        print(f"  - {len(result.ir.workflows)} workflows")
    else:
        print(f"\n✗ Compilation failed:")
        for error in result.errors:
            print(f"  - {error}")
