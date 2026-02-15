"""
Axiom React Generator

Generates production-quality React + TypeScript code from Axiom IR
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


# ============================================================================
# GENERATED ARTIFACTS
# ============================================================================

@dataclass
class TypeScriptFile:
    """Generated TypeScript file"""
    path: str
    content: str

@dataclass
class FrontendArtifacts:
    """Complete frontend codebase"""
    components: list[TypeScriptFile]
    router: TypeScriptFile
    api_client: TypeScriptFile
    types: TypeScriptFile
    hooks: list[TypeScriptFile]
    package_json: dict
    tsconfig: dict
    vite_config: TypeScriptFile


# ============================================================================
# REACT GENERATOR
# ============================================================================

class ReactGenerator:
    """
    Generates React components from ViewSpec
    
    Input: ViewSpec with state, layout, actions
    Output: TypeScript React component with hooks, state management
    """
    
    def __init__(self):
        self.indent_level = 0
    
    def generate(self, ir: 'AxiomIR') -> FrontendArtifacts:
        """Generate complete frontend codebase"""
        
        # Generate components for each view
        components = []
        for view_name, view in ir.views.items():
            component = self._generate_component(view)
            components.append(component)
        
        # Generate router
        router = self._generate_router(list(ir.views.values()))
        
        # Generate API client
        api_client = self._generate_api_client(ir.api_routes)
        
        # Generate TypeScript types
        types = self._generate_types(ir)
        
        # Generate custom hooks
        hooks = self._generate_hooks(ir)
        
        # Generate package.json
        package_json = self._generate_package_json(ir)
        
        # Generate tsconfig.json
        tsconfig = self._generate_tsconfig()
        
        # Generate vite.config.ts
        vite_config = self._generate_vite_config()
        
        return FrontendArtifacts(
            components=components,
            router=router,
            api_client=api_client,
            types=types,
            hooks=hooks,
            package_json=package_json,
            tsconfig=tsconfig,
            vite_config=vite_config
        )
    
    def _generate_component(self, view: 'ViewSpec') -> TypeScriptFile:
        """Generate single React component from ViewSpec"""
        
        # Build imports
        imports = self._generate_imports(view)
        
        # Generate state interface
        state_interface = self._generate_state_interface(view)
        
        # Generate component function
        component_body = self._generate_component_body(view)
        
        # Combine all parts
        content = f"""{imports}

{state_interface}

export function {view.name}() {{
{self._indent(component_body, 1)}
}}
"""
        
        return TypeScriptFile(
            path=f"src/views/{view.name}.tsx",
            content=content
        )
    
    def _generate_imports(self, view: 'ViewSpec') -> str:
        """Generate import statements"""
        
        imports = [
            "import { useState, useEffect } from 'react';",
            "import { useAxiomState, useAxiomAction } from '@/lib/axiom-runtime';",
        ]
        
        # Determine which UI components are used
        ui_components = self._extract_ui_components(view.layout)
        if ui_components:
            imports.append(
                f"import {{ {', '.join(ui_components)} }} from '@/components/ui';"
            )
        
        # Add type imports
        type_names = self._extract_type_names(view)
        if type_names:
            imports.append(
                f"import type {{ {', '.join(type_names)} }} from '@/types';"
            )
        
        return "\n".join(imports)
    
    def _generate_state_interface(self, view: 'ViewSpec') -> str:
        """Generate TypeScript interface for component state"""
        
        if not view.state:
            return ""
        
        fields = []
        for field_name, field in view.state.items():
            ts_type = self._convert_type_to_ts(field.type_info)
            fields.append(f"  {field_name}: {ts_type};")
        
        return f"""interface {view.name}State {{
{chr(10).join(fields)}
}}"""
    
    def _generate_component_body(self, view: 'ViewSpec') -> str:
        """Generate component body with state, actions, and JSX"""
        
        parts = []
        
        # State management
        initial_state = json.dumps(view.initial_state, indent=2)
        parts.append(f"""const [state, setState] = useAxiomState<{view.name}State>({initial_state});""")
        
        # Generate action hooks
        for action in view.actions:
            action_hook = self._generate_action_hook(action)
            parts.append(action_hook)
        
        # Lifecycle hooks
        if "on_mount" in view.lifecycle_hooks:
            parts.append(self._generate_lifecycle_hook("on_mount", view))
        
        # JSX rendering
        jsx = self._layout_to_jsx(view.layout)
        parts.append(f"\nreturn (\n{self._indent(jsx, 1)}\n);")
        
        return "\n\n".join(parts)
    
    def _generate_action_hook(self, action: 'ActionSpec') -> str:
        """
        Generate custom hook for action
        
        Example output:
        const { execute: triggerAnalysis, loading: triggerAnalysisLoading } = useAxiomAction(
          'trigger_analysis',
          async () => {
            setState(prev => ({ ...prev, loading: true }));
            const result = await apiClient.post('/api/analyze', {...});
            setState(prev => ({ ...prev, analysis: result, loading: false }));
          },
          { debounce: 300 }
        );
        """
        
        # Extract action body (simplified - would parse actual AST)
        action_body = "// Action implementation"
        
        options = {}
        if action.debounce:
            options["debounce"] = action.debounce
        if action.throttle:
            options["throttle"] = action.throttle
        
        options_str = json.dumps(options) if options else ""
        
        return f"""const {{ execute: {action.name}, loading: {action.name}Loading }} = useAxiomAction(
  '{action.name}',
  async () => {{
    {action_body}
  }}{', ' + options_str if options_str else ''}
);"""
    
    def _generate_lifecycle_hook(self, hook_name: str, view: 'ViewSpec') -> str:
        """Generate lifecycle hook (useEffect)"""
        
        if hook_name == "on_mount":
            return """useEffect(() => {
  // Load initial data
  (async () => {
    const companies = await fetch('/api/companies').then(r => r.json());
    setState(prev => ({ ...prev, companies }));
  })();
}, []);"""
        
        return ""
    
    def _layout_to_jsx(self, layout: 'LayoutNode') -> str:
        """
        Convert layout tree to JSX
        
        Example:
        Container([
            Row([
                Column(width=6, children=[Button(...)])
            ])
        ])
        
        Becomes:
        <Container>
          <Row>
            <Column width={6}>
              <Button ... />
            </Column>
          </Row>
        </Container>
        """
        
        if not layout:
            return "<div>No layout defined</div>"
        
        return self._node_to_jsx(layout)
    
    def _node_to_jsx(self, node: 'LayoutNode', depth: int = 0) -> str:
        """Convert single layout node to JSX"""
        
        # Convert props to JSX attributes
        props_str = self._props_to_jsx_attributes(node.props)
        
        # Self-closing if no children
        if not node.children:
            return f"<{node.component}{props_str} />"
        
        # With children
        children_jsx = [
            self._node_to_jsx(child, depth + 1)
            for child in node.children
        ]
        
        children_str = "\n".join([
            self._indent(child, depth + 1)
            for child in children_jsx
        ])
        
        return f"""<{node.component}{props_str}>
{children_str}
</{node.component}>"""
    
    def _props_to_jsx_attributes(self, props: dict[str, Any]) -> str:
        """Convert Python props dict to JSX attributes"""
        
        if not props:
            return ""
        
        attrs = []
        for key, value in props.items():
            # Convert snake_case to camelCase
            jsx_key = self._to_camel_case(key)
            
            # Handle different value types
            if isinstance(value, bool):
                if value:
                    attrs.append(jsx_key)  # Boolean true
                continue
            elif isinstance(value, str):
                attrs.append(f'{jsx_key}="{value}"')
            elif isinstance(value, (int, float)):
                attrs.append(f'{jsx_key}={{{value}}}')
            elif callable(value):
                attrs.append(f'{jsx_key}={{{value.__name__}}}')
            else:
                # Complex object - use JSON
                attrs.append(f'{jsx_key}={{{json.dumps(value)}}}')
        
        return " " + " ".join(attrs) if attrs else ""
    
    def _generate_router(self, views: list['ViewSpec']) -> TypeScriptFile:
        """Generate React Router configuration"""
        
        routes = []
        for view in views:
            auth_wrapper = "ProtectedRoute" if view.auth_required else "React.Fragment"
            routes.append(f"""  {{
    path: '{view.route}',
    element: <{auth_wrapper}><{view.name} /></{auth_wrapper}>
  }}""")
        
        content = f"""import {{ createBrowserRouter, RouterProvider }} from 'react-router-dom';
import {{ ProtectedRoute }} from '@/components/ProtectedRoute';
{chr(10).join([f"import {{ {v.name} }} from '@/views/{v.name}';" for v in views])}

const router = createBrowserRouter([
{',\n'.join(routes)}
]);

export function AppRouter() {{
  return <RouterProvider router={{router}} />;
}}
"""
        
        return TypeScriptFile(
            path="src/router.tsx",
            content=content
        )
    
    def _generate_api_client(self, routes: list['RouteSpec']) -> TypeScriptFile:
        """Generate typed API client"""
        
        methods = []
        for route in routes:
            method_name = route.handler_name
            http_method = route.methods[0].lower()
            
            # Generate parameters
            params = [
                f"{p.name}: {self._convert_type_to_ts(p.type_info)}"
                for p in route.parameters
            ]
            params_str = ", ".join(params)
            
            # Generate return type (simplified)
            return_type = "Promise<any>"
            
            methods.append(f"""  async {method_name}({params_str}): {return_type} {{
    return this.request('{http_method}', '{route.path}', {{ {', '.join([p.name for p in route.parameters])} }});
  }}""")
        
        content = f"""class APIClient {{
  private baseURL: string;
  
  constructor(baseURL: string = '/api') {{
    this.baseURL = baseURL;
  }}
  
  private async request(method: string, path: string, data?: any): Promise<any> {{
    const response = await fetch(`${{this.baseURL}}${{path}}`, {{
      method: method.toUpperCase(),
      headers: {{
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${{localStorage.getItem('token')}}`
      }},
      body: data ? JSON.stringify(data) : undefined
    }});
    
    if (!response.ok) {{
      throw new Error(`API error: ${{response.statusText}}`);
    }}
    
    return response.json();
  }}

{chr(10).join(methods)}
}}

export const apiClient = new APIClient();
"""
        
        return TypeScriptFile(
            path="src/lib/api-client.ts",
            content=content
        )
    
    def _generate_types(self, ir: 'AxiomIR') -> TypeScriptFile:
        """Generate TypeScript type definitions"""
        
        # This would extract all types from IR and generate interfaces
        content = """// Generated TypeScript types

export interface Company {
  id: string;
  name: string;
  ticker: string;
  sector: string;
  market_cap: number;
}

export interface CompanyAnalysis {
  company_id: string;
  analysis_type: string;
  summary: string;
  metrics: Record<string, any>;
  insights: string[];
  risks: string[];
  opportunities: string[];
  confidence_score: number;
  timestamp: string;
}
"""
        
        return TypeScriptFile(
            path="src/types/index.ts",
            content=content
        )
    
    def _generate_hooks(self, ir: 'AxiomIR') -> list[TypeScriptFile]:
        """Generate custom React hooks"""
        
        # Generate useAxiomState hook
        axiom_state_hook = TypeScriptFile(
            path="src/lib/axiom-runtime/useAxiomState.ts",
            content="""import { useState, Dispatch, SetStateAction } from 'react';

export function useAxiomState<T>(initialState: T): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState<T>(initialState);
  
  // In production, this would integrate with server-driven UI
  // and sync state with backend
  
  return [state, setState];
}
"""
        )
        
        # Generate useAxiomAction hook
        axiom_action_hook = TypeScriptFile(
            path="src/lib/axiom-runtime/useAxiomAction.ts",
            content="""import { useState, useCallback, useRef, useEffect } from 'react';

interface ActionOptions {
  debounce?: number;
  throttle?: number;
}

export function useAxiomAction<T extends (...args: any[]) => Promise<any>>(
  name: string,
  action: T,
  options?: ActionOptions
) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const debounceTimer = useRef<NodeJS.Timeout>();
  
  const execute = useCallback(async (...args: Parameters<T>) => {
    // Handle debouncing
    if (options?.debounce) {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
      
      return new Promise<Awaited<ReturnType<T>>>((resolve, reject) => {
        debounceTimer.current = setTimeout(async () => {
          try {
            setLoading(true);
            setError(null);
            const result = await action(...args);
            setLoading(false);
            resolve(result);
          } catch (err) {
            setError(err as Error);
            setLoading(false);
            reject(err);
          }
        }, options.debounce);
      });
    }
    
    // Normal execution
    try {
      setLoading(true);
      setError(null);
      const result = await action(...args);
      setLoading(false);
      return result;
    } catch (err) {
      setError(err as Error);
      setLoading(false);
      throw err;
    }
  }, [action, options]);
  
  useEffect(() => {
    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, []);
  
  return { execute, loading, error };
}
"""
        )
        
        return [axiom_state_hook, axiom_action_hook]
    
    def _generate_package_json(self, ir: 'AxiomIR') -> dict:
        """Generate package.json"""
        
        return {
            "name": ir.app_metadata.name,
            "version": ir.app_metadata.version,
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
                "preview": "vite preview",
                "lint": "eslint . --ext ts,tsx"
            },
            "dependencies": {
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
                "react-router-dom": "^6.22.0",
                "@radix-ui/react-alert-dialog": "^1.0.5",
                "@radix-ui/react-tabs": "^1.0.4",
                "recharts": "^2.12.0",
                "lucide-react": "^0.363.0"
            },
            "devDependencies": {
                "@types/react": "^18.3.1",
                "@types/react-dom": "^18.3.0",
                "@vitejs/plugin-react": "^4.2.1",
                "typescript": "^5.4.5",
                "vite": "^5.2.0",
                "tailwindcss": "^3.4.3",
                "autoprefixer": "^10.4.19",
                "postcss": "^8.4.38"
            }
        }
    
    def _generate_tsconfig(self) -> dict:
        """Generate tsconfig.json"""
        
        return {
            "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": True,
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "skipLibCheck": True,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": True,
                "resolveJsonModule": True,
                "isolatedModules": True,
                "noEmit": True,
                "jsx": "react-jsx",
                "strict": True,
                "noUnusedLocals": True,
                "noUnusedParameters": True,
                "noFallthroughCasesInSwitch": True,
                "paths": {
                    "@/*": ["./src/*"]
                }
            },
            "include": ["src"],
            "references": [{"path": "./tsconfig.node.json"}]
        }
    
    def _generate_vite_config(self) -> TypeScriptFile:
        """Generate vite.config.ts"""
        
        content = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
"""
        
        return TypeScriptFile(
            path="vite.config.ts",
            content=content
        )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _indent(self, text: str, level: int) -> str:
        """Indent text by level"""
        indent = "  " * level
        return "\n".join(indent + line for line in text.split("\n"))
    
    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
    
    def _convert_type_to_ts(self, type_info: 'TypeInfo') -> str:
        """Convert Python type to TypeScript type"""
        
        type_map = {
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "dict": "Record<string, any>",
            "Any": "any"
        }
        
        ts_type = type_map.get(type_info.name, type_info.name)
        
        if type_info.is_optional:
            ts_type = f"{ts_type} | null"
        
        if type_info.is_list and type_info.generic_args:
            inner = self._convert_type_to_ts(type_info.generic_args[0])
            ts_type = f"{inner}[]"
        
        return ts_type
    
    def _extract_ui_components(self, layout: 'LayoutNode') -> set[str]:
        """Extract all UI component names used in layout"""
        
        components = {layout.component}
        for child in layout.children:
            components.update(self._extract_ui_components(child))
        
        return components
    
    def _extract_type_names(self, view: 'ViewSpec') -> set[str]:
        """Extract type names used in view"""
        
        types = set()
        for field in view.state.values():
            if field.type_info.name not in ["str", "int", "float", "bool", "dict", "list"]:
                types.add(field.type_info.name)
        
        return types


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    from compiler import AxiomCompiler
    from pathlib import Path
    
    # Compile application
    compiler = AxiomCompiler(project_root=Path.cwd())
    result = compiler.compile(entrypoint=Path("app.py"))
    
    if result.success:
        # Generate React code
        generator = ReactGenerator()
        artifacts = generator.generate(result.ir)
        
        # Write to disk
        output_dir = Path("dist/frontend")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for component in artifacts.components:
            component_path = output_dir / component.path
            component_path.parent.mkdir(parents=True, exist_ok=True)
            component_path.write_text(component.content)
        
        print(f"✓ Generated {len(artifacts.components)} React components")
