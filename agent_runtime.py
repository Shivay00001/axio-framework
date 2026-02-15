"""
Axiom Agent Runtime: Core Execution Engine

Handles:
- Agent initialization and lifecycle
- Reasoning loop with LLM
- Tool orchestration via MCP
- Memory integration
- Observability and tracing
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from uuid import uuid4
from datetime import datetime
from enum import Enum

# Placeholder imports - in real implementation these would be actual libraries
from opentelemetry import trace
from anthropic import AsyncAnthropic


# ============================================================================
# DATA MODELS
# ============================================================================

class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class ToolCall:
    """Represents a single tool invocation"""
    id: str
    name: str
    arguments: dict
    
@dataclass
class ToolResult:
    """Result from tool execution"""
    tool_call_id: str
    output: Any
    is_error: bool = False
    error_message: Optional[str] = None
    execution_time_ms: float = 0

@dataclass
class ExecutionContext:
    """Context for a single agent execution"""
    execution_id: str
    agent_id: str
    user_id: Optional[str] = None
    query: Optional[str] = None
    entity_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

@dataclass
class MemoryContext:
    """Memory loaded for execution"""
    similar: list[dict] = field(default_factory=list)
    related: list[dict] = field(default_factory=list)
    cached: list[dict] = field(default_factory=list)

@dataclass
class AgentResult:
    """Result from agent execution"""
    output: Any
    execution_id: str
    status: ExecutionStatus
    iterations: int
    tool_calls: list[ToolCall]
    tokens_used: int
    execution_time_ms: float
    memory_updates: list[dict] = field(default_factory=list)
    trace_id: Optional[str] = None

@dataclass
class LoopResult:
    """Result from reasoning loop"""
    output: Any
    iterations: int
    tool_calls: list[ToolCall]
    tokens_used: int
    memory_updates: list[dict]


# ============================================================================
# REASONING LOOP
# ============================================================================

class ReasoningLoop:
    """
    Core LLM reasoning loop with tool orchestration
    
    This implements the ReAct pattern:
    - Reason: LLM thinks about what to do
    - Act: LLM decides to use tools
    - Observe: LLM sees tool results
    - Repeat until task complete
    """
    
    def __init__(
        self,
        model_client: AsyncAnthropic,
        tools_registry: 'ToolRegistry',
        memory_context: MemoryContext,
        config: dict,
        tracer: trace.Tracer
    ):
        self.model = model_client
        self.tools = tools_registry
        self.memory = memory_context
        self.config = config
        self.tracer = tracer
        
        self.max_iterations = config.get("max_iterations", 10)
        self.temperature = config.get("temperature", 0.1)
        self.tool_parallelism = config.get("tool_parallelism", True)
        self.reflection_enabled = config.get("reflection_enabled", False)
    
    async def run(
        self,
        method_spec: 'MethodSpec',
        args: dict
    ) -> LoopResult:
        """
        Execute reasoning loop
        
        Pattern:
        1. Call LLM with task + available tools
        2. If LLM requests tools → execute them → add results to context
        3. Repeat until LLM produces final answer or max iterations reached
        4. Extract memory updates from conversation
        """
        
        with self.tracer.start_as_current_span("reasoning_loop") as span:
            span.set_attribute("method", method_spec.name)
            span.set_attribute("max_iterations", self.max_iterations)
            
            # Build initial messages
            messages = [
                {
                    "role": "user",
                    "content": self._format_task(method_spec, args)
                }
            ]
            
            # Add memory context to first message
            if self.memory.similar or self.memory.related:
                messages[0]["content"] += f"\n\nRelevant context from memory:\n{self._format_memory_context()}"
            
            iterations = 0
            tool_calls_log = []
            total_tokens = 0
            
            while iterations < self.max_iterations:
                with self.tracer.start_as_current_span(f"iteration_{iterations}"):
                    # Call LLM
                    response = await self._call_model(messages)
                    total_tokens += response.usage.input_tokens + response.usage.output_tokens
                    
                    # Extract content
                    content = self._extract_content(response)
                    tool_calls = self._extract_tool_calls(response)
                    
                    # Check if LLM wants to use tools
                    if tool_calls:
                        span.add_event(f"Tool calls requested: {len(tool_calls)}")
                        
                        # Execute tools
                        tool_results = await self._execute_tools(
                            tool_calls,
                            parallel=self.tool_parallelism
                        )
                        
                        tool_calls_log.extend(tool_calls)
                        
                        # Add assistant message with tool calls
                        messages.append({
                            "role": "assistant",
                            "content": content if content else "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.name,
                                        "arguments": json.dumps(tc.arguments)
                                    }
                                }
                                for tc in tool_calls
                            ]
                        })
                        
                        # Add tool results
                        for tool_call, result in zip(tool_calls, tool_results):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result.output) if not result.is_error else result.error_message
                            })
                        
                        # Continue loop
                        iterations += 1
                        continue
                    
                    # No more tools - check if we have final answer
                    if content:
                        span.add_event("Final answer received")
                        break
                    
                    # Neither tools nor content - something's wrong
                    span.add_event("No tools or content, ending loop")
                    break
                
                iterations += 1
            
            # Extract structured output from final message
            output = self._parse_output(content, method_spec.return_type)
            
            # Extract memory updates from conversation
            memory_updates = await self._extract_memory_updates(
                messages=messages,
                method_spec=method_spec
            )
            
            span.set_attribute("iterations", iterations)
            span.set_attribute("tool_calls", len(tool_calls_log))
            span.set_attribute("tokens_used", total_tokens)
            
            return LoopResult(
                output=output,
                iterations=iterations,
                tool_calls=tool_calls_log,
                tokens_used=total_tokens,
                memory_updates=memory_updates
            )
    
    async def _call_model(self, messages: list[dict]) -> Any:
        """Call LLM with messages and tools"""
        
        # Build system prompt
        system_prompt = self._build_system_prompt()
        
        # Get tool schemas
        tools = self.tools.get_schemas()
        
        # Call Claude (or other model)
        response = await self.model.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            temperature=self.temperature,
            system=system_prompt,
            messages=messages,
            tools=tools if tools else None
        )
        
        return response
    
    async def _execute_tools(
        self,
        tool_calls: list[ToolCall],
        parallel: bool = True
    ) -> list[ToolResult]:
        """Execute tool calls via MCP"""
        
        if parallel and len(tool_calls) > 1:
            # Execute in parallel for speed
            tasks = [
                self._execute_single_tool(call)
                for call in tool_calls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert exceptions to error results
            final_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    final_results.append(ToolResult(
                        tool_call_id=tool_calls[i].id,
                        output=None,
                        is_error=True,
                        error_message=str(result)
                    ))
                else:
                    final_results.append(result)
            
            return final_results
        else:
            # Sequential execution
            results = []
            for call in tool_calls:
                result = await self._execute_single_tool(call)
                results.append(result)
            return results
    
    async def _execute_single_tool(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call"""
        
        start_time = datetime.now()
        
        try:
            output = await self.tools.execute(
                tool_name=call.name,
                arguments=call.arguments
            )
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return ToolResult(
                tool_call_id=call.id,
                output=output,
                is_error=False,
                execution_time_ms=execution_time
            )
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return ToolResult(
                tool_call_id=call.id,
                output=None,
                is_error=True,
                error_message=str(e),
                execution_time_ms=execution_time
            )
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for agent"""
        
        return f"""You are an AI agent executing a specific task.

Available tools:
{self._format_tool_descriptions()}

Instructions:
1. Think step-by-step about the task
2. Use tools to gather information as needed
3. You can call multiple tools in parallel if they're independent
4. Produce a final answer in the required format
5. Be thorough but efficient

Remember: You have access to relevant context from memory, use it to inform your decisions.
"""
    
    def _format_task(self, method_spec: 'MethodSpec', args: dict) -> str:
        """Format task description for LLM"""
        
        return f"""Task: {method_spec.name}

Description: {method_spec.docstring}

Arguments:
{json.dumps(args, indent=2)}

Please execute this task step by step. Use available tools as needed.
"""
    
    def _format_tool_descriptions(self) -> str:
        """Format tool descriptions for system prompt"""
        
        descriptions = []
        for tool_name, tool in self.tools.tools.items():
            descriptions.append(f"- {tool_name}: {tool.description}")
        
        return "\n".join(descriptions)
    
    def _format_memory_context(self) -> str:
        """Format memory context for LLM"""
        
        parts = []
        
        if self.memory.similar:
            parts.append("Similar past experiences:")
            for item in self.memory.similar[:5]:
                parts.append(f"  - {item.get('content', '')}")
        
        if self.memory.related:
            parts.append("\nRelated information:")
            for item in self.memory.related[:5]:
                parts.append(f"  - {item.get('content', '')}")
        
        return "\n".join(parts)
    
    def _extract_content(self, response: Any) -> Optional[str]:
        """Extract text content from model response"""
        
        for block in response.content:
            if block.type == "text":
                return block.text
        
        return None
    
    def _extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Extract tool calls from model response"""
        
        tool_calls = []
        
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))
        
        return tool_calls
    
    def _parse_output(self, content: str, return_type: 'TypeInfo') -> Any:
        """Parse final output according to expected return type"""
        
        # Try to extract JSON if return type is structured
        if return_type.name not in ["str", "int", "float", "bool"]:
            try:
                # Look for JSON in content
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    return json.loads(json_str)
                elif content.strip().startswith("{") or content.strip().startswith("["):
                    return json.loads(content)
            except:
                pass
        
        # Return as-is if can't parse
        return content
    
    async def _extract_memory_updates(
        self,
        messages: list[dict],
        method_spec: 'MethodSpec'
    ) -> list[dict]:
        """
        Extract memory updates from conversation
        
        This looks at the conversation and identifies new facts,
        insights, or relationships that should be stored in memory
        """
        
        # Simplified implementation
        # In production, this would use an LLM call to extract structured updates
        
        updates = []
        
        # For now, just extract tool results as potential memory
        for msg in messages:
            if msg.get("role") == "tool":
                updates.append({
                    "type": "tool_result",
                    "content": msg.get("content", ""),
                    "timestamp": datetime.now().isoformat()
                })
        
        return updates


# ============================================================================
# AGENT RUNTIME
# ============================================================================

class AgentRuntime:
    """
    Core agent execution engine
    
    Responsibilities:
    - Execute reasoning loops with LLM
    - Orchestrate tool calls (MCP)
    - Manage memory operations
    - Provide observability/tracing
    - Handle context isolation
    """
    
    def __init__(
        self,
        spec: 'AgentSpec',
        model_client: AsyncAnthropic,
        memory_engine: 'MemoryEngine',
        tools_registry: 'ToolRegistry',
        tracer: trace.Tracer
    ):
        self.spec = spec
        self.model = model_client
        self.memory = memory_engine
        self.tools = tools_registry
        self.tracer = tracer
        
        # Filter tools to only those configured for this agent
        self.agent_tools = self._filter_tools()
    
    def _filter_tools(self) -> 'ToolRegistry':
        """Create filtered tool registry for this agent"""
        
        # In production, this would create a new registry with only
        # the tools specified in self.spec.tools
        return self.tools
    
    async def execute(
        self,
        method: str,
        args: dict,
        context: ExecutionContext
    ) -> AgentResult:
        """
        Execute agent method with full reasoning loop
        
        Flow:
        1. Load memory context
        2. Initialize reasoning loop
        3. Execute with tracing
        4. Store memory updates
        5. Return result
        """
        
        start_time = datetime.now()
        
        with self.tracer.start_as_current_span(f"agent.{self.spec.name}.{method}") as span:
            span.set_attribute("agent", self.spec.name)
            span.set_attribute("method", method)
            span.set_attribute("execution_id", context.execution_id)
            
            try:
                # 1. Load memory context
                memory_ctx = await self._load_memory_context(context)
                
                # 2. Get method spec
                if method not in self.spec.methods:
                    raise ValueError(f"Method {method} not found on agent {self.spec.name}")
                
                method_spec = self.spec.methods[method]
                
                # 3. Initialize reasoning loop
                loop = ReasoningLoop(
                    model_client=self.model,
                    tools_registry=self.agent_tools,
                    memory_context=memory_ctx,
                    config=self.spec.reasoning_config.__dict__,
                    tracer=self.tracer
                )
                
                # 4. Execute method
                result = await loop.run(
                    method_spec=method_spec,
                    args=args
                )
                
                # 5. Store memory updates
                if result.memory_updates:
                    await self.memory.store_batch(
                        agent_id=self.spec.name,
                        updates=result.memory_updates
                    )
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return AgentResult(
                    output=result.output,
                    execution_id=context.execution_id,
                    status=ExecutionStatus.SUCCESS,
                    iterations=result.iterations,
                    tool_calls=result.tool_calls,
                    tokens_used=result.tokens_used,
                    execution_time_ms=execution_time,
                    memory_updates=result.memory_updates,
                    trace_id=span.get_span_context().trace_id
                )
            
            except Exception as e:
                span.record_exception(e)
                span.set_attribute("error", True)
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return AgentResult(
                    output=None,
                    execution_id=context.execution_id,
                    status=ExecutionStatus.FAILED,
                    iterations=0,
                    tool_calls=[],
                    tokens_used=0,
                    execution_time_ms=execution_time,
                    trace_id=span.get_span_context().trace_id
                )
    
    async def _load_memory_context(
        self,
        context: ExecutionContext
    ) -> MemoryContext:
        """Load relevant memory for this execution"""
        
        if not self.spec.memory_schema:
            return MemoryContext()
        
        # Vector similarity search
        similar = []
        if context.query:
            similar = await self.memory.vector_search(
                agent_id=self.spec.name,
                query=context.query,
                k=10
            )
        
        # Graph traversal for relationships
        related = []
        if context.entity_ids:
            related = await self.memory.graph_traverse(
                start_nodes=context.entity_ids,
                depth=2
            )
        
        # Check cache
        cached = []
        if context.query:
            cache_key = f"{self.spec.name}:{context.query}"
            cached_result = await self.memory.cache_get(cache_key)
            if cached_result:
                cached = [cached_result]
        
        return MemoryContext(
            similar=similar,
            related=related,
            cached=cached
        )


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Example of how to use AgentRuntime"""
    
    from compiler import AgentSpec, MethodSpec, ReasoningConfig, TypeInfo
    
    # Create agent spec (normally comes from compiler)
    spec = AgentSpec(
        name="research_agent",
        model="claude-sonnet-4",
        memory_schema=None,
        tools=[],
        methods={
            "analyze": MethodSpec(
                name="analyze",
                parameters=[],
                return_type=TypeInfo(name="dict"),
                docstring="Analyze company",
                body=None,
                has_reasoning=True
            )
        },
        reasoning_config=ReasoningConfig(
            max_iterations=10,
            temperature=0.1
        ),
        docstring="Research agent"
    )
    
    # Initialize runtime
    model = AsyncAnthropic(api_key="your-key")
    tracer = trace.get_tracer(__name__)
    
    runtime = AgentRuntime(
        spec=spec,
        model_client=model,
        memory_engine=None,  # Would be real MemoryEngine
        tools_registry=None,  # Would be real ToolRegistry
        tracer=tracer
    )
    
    # Execute
    context = ExecutionContext(
        execution_id=str(uuid4()),
        agent_id="research_agent",
        query="analyze Apple Inc"
    )
    
    result = await runtime.execute(
        method="analyze",
        args={"company_id": "AAPL"},
        context=context
    )
    
    print(f"Result: {result.output}")
    print(f"Iterations: {result.iterations}")
    print(f"Tokens used: {result.tokens_used}")


if __name__ == "__main__":
    asyncio.run(example_usage())
