"""LangGraph-based Kubernetes troubleshooting agent - Gemini compatible (no bind_tools)."""
from typing import Literal, Dict, Any, List, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from models.ai import get_llm
from core.k8s_tools import get_k8s_tools
import structlog
import operator

logger = structlog.get_logger()


# ---------------------------------------------------------
# Convert LangChain StructuredTool → OpenAI JSON Schema tool
# ---------------------------------------------------------
def convert_tools_to_openai_format(tools):
    formatted = []
    for t in tools:
        schema = (
            t.args_schema.schema()
            if getattr(t, "args_schema", None)
            else {"type": "object", "properties": {}, "required": []}
        )

        formatted.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": schema
            }
        })

    return formatted


class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    namespace: str


KUBERNETES_EXPERT_PROMPT = """You are an expert Kubernetes troubleshooting assistant.

Namespace: {namespace}

Available Tools:
- list_pods
- get_pod_logs
- get_pod_events
- describe_pod
- list_deployments
- get_nodes
- list_namespaces

You MUST use tools when needed.
Always provide structured markdown output with Summary, Details, Issues, Recommendations.
"""


class KubernetesTroubleshootingAgent:
    """LangGraph agent designed for Gemini (OpenAI-compatible API)."""

    def __init__(self, kubeconfig_path: str = None):
        self.llm = get_llm()

        # LangChain StructuredTools
        self.tools = get_k8s_tools(kubeconfig_path)
        self.tools_by_name = {tool.name: tool for tool in self.tools}

        # Convert to OpenAI JSON schema
        self.openai_tools = convert_tools_to_openai_format(self.tools)

        self.namespace = "default"
        self.graph = self._build_graph()

        logger.info("LangGraph agent initialized", tools_count=len(self.tools))

    # -----------------------------------------------------
    # Build Graph
    # -----------------------------------------------------
    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self._call_agent)
        workflow.add_node("tools", self._execute_tools)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END}
        )

        workflow.add_edge("tools", "agent")

        return workflow.compile()

    # -----------------------------------------------------
    # Call LLM with tools
    # -----------------------------------------------------
    def _call_agent(self, state: AgentState):
        logger.info("Calling agent")

        namespace = state["namespace"]
        messages = state["messages"]

        # Ensure system prompt
        if not any(isinstance(m, SystemMessage) for m in messages):
            sys_msg = SystemMessage(content=KUBERNETES_EXPERT_PROMPT.format(namespace=namespace))
            messages = [sys_msg] + list(messages)

        # Call Gemini using OpenAI-compatible tools
        response = self.llm.invoke(
            messages,
            tools=self.openai_tools,   # <-- Correct format
            tool_choice="auto"
        )

        return {"messages": [response]}

    # -----------------------------------------------------
    # Should the graph continue to tools?
    # -----------------------------------------------------
    def _should_continue(self, state: AgentState) -> Literal["continue", "end"]:
        last_msg = state["messages"][-1]

        # Gemini tool calls come through last_msg.tool_calls
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "continue"

        return "end"

    # -----------------------------------------------------
    # Execute tool calls
    # -----------------------------------------------------
    def _execute_tools(self, state: AgentState):
        logger.info("Executing tools")

        last_msg = state["messages"][-1]
        tool_outputs = []

        for call in last_msg.tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            call_id = call["id"]

            logger.info("Executing tool", tool=tool_name, args=tool_args)

            try:
                tool = self.tools_by_name.get(tool_name)

                if not tool:
                    result = f"Tool '{tool_name}' not found."
                else:
                    result = tool.invoke(tool_args)

                tool_outputs.append(
                    ToolMessage(
                        content=str(result),
                        name=tool_name,
                        tool_call_id=call_id
                    )
                )

            except Exception as e:
                logger.error("Tool execution failed", error=str(e))
                tool_outputs.append(
                    ToolMessage(
                        content=f"Error executing {tool_name}: {str(e)}",
                        name=tool_name,
                        tool_call_id=call_id
                    )
                )

        return {"messages": tool_outputs}

    # -----------------------------------------------------
    # Public query method
    # -----------------------------------------------------
    async def query(self, query: str, namespace: str = "default", context=None):
        logger.info("Processing query", query=query, namespace=namespace)

        self.namespace = namespace

        state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "namespace": namespace
        }

        try:
            result = await self.graph.ainvoke(state)

            final = result["messages"][-1]
            text = final.content if hasattr(final, "content") else str(final)

            tools_used = len([m for m in result["messages"] if isinstance(m, ToolMessage)])

            return {
                "response": text,
                "analysis": {
                    "status": "completed",
                    "namespace": namespace,
                    "tools_used": tools_used
                },
                "suggestions": self._extract_suggestions(text),
                "success": True
            }

        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "response": f"Failure: {str(e)}",
                "analysis": {"status": "failed", "error": str(e)},
                "suggestions": ["Try specifying a namespace", "Check cluster connectivity"],
                "success": False
            }

    # -----------------------------------------------------
    # Suggestion extraction
    # -----------------------------------------------------
    def _extract_suggestions(self, text: str):
        result = []
        for line in text.split("\n"):
            if line.startswith("- ") and any(
                kw in line.lower() for kw in ["recommend", "should", "check", "try", "consider"]
            ):
                result.append(line[2:].strip())
        return result[:5]


# Global singleton
_agent_instance = None


def get_agent(kubeconfig_path=None):
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = KubernetesTroubleshootingAgent(kubeconfig_path)
    return _agent_instance
"""LangGraph-based Kubernetes troubleshooting agent - Gemini compatible (no bind_tools)."""
from typing import Literal, Dict, Any, List, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from models.ai import get_llm
from core.k8s_tools import get_k8s_tools
import structlog
import operator

logger = structlog.get_logger()


# ---------------------------------------------------------
# Convert LangChain StructuredTool → OpenAI JSON Schema tool
# ---------------------------------------------------------
def convert_tools_to_openai_format(tools):
    formatted = []
    for t in tools:
        schema = (
            t.args_schema.schema()
            if getattr(t, "args_schema", None)
            else {"type": "object", "properties": {}, "required": []}
        )

        formatted.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": schema
            }
        })

    return formatted


class AgentState(TypedDict):
    messages: Annotated[List, operator.add]
    namespace: str


KUBERNETES_EXPERT_PROMPT = """You are an expert Kubernetes troubleshooting assistant.

Namespace: {namespace}

Available Tools:
- list_pods
- get_pod_logs
- get_pod_events
- describe_pod
- list_deployments
- get_nodes
- list_namespaces

You MUST use tools when needed.
Always provide structured markdown output with Summary, Details, Issues, Recommendations.
"""


class KubernetesTroubleshootingAgent:
    """LangGraph agent designed for Gemini (OpenAI-compatible API)."""

    def __init__(self, kubeconfig_path: str = None):
        self.llm = get_llm()

        # LangChain StructuredTools
        self.tools = get_k8s_tools(kubeconfig_path)
        self.tools_by_name = {tool.name: tool for tool in self.tools}

        # Convert to OpenAI JSON schema
        self.openai_tools = convert_tools_to_openai_format(self.tools)

        self.namespace = "default"
        self.graph = self._build_graph()

        logger.info("LangGraph agent initialized", tools_count=len(self.tools))

    # -----------------------------------------------------
    # Build Graph
    # -----------------------------------------------------
    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self._call_agent)
        workflow.add_node("tools", self._execute_tools)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END}
        )

        workflow.add_edge("tools", "agent")

        return workflow.compile()

    # -----------------------------------------------------
    # Call LLM with tools
    # -----------------------------------------------------
    def _call_agent(self, state: AgentState):
        logger.info("Calling agent")

        namespace = state["namespace"]
        messages = state["messages"]

        # Ensure system prompt
        if not any(isinstance(m, SystemMessage) for m in messages):
            sys_msg = SystemMessage(content=KUBERNETES_EXPERT_PROMPT.format(namespace=namespace))
            messages = [sys_msg] + list(messages)

        # Call Gemini using OpenAI-compatible tools
        response = self.llm.invoke(
            messages,
            tools=self.openai_tools,   # <-- Correct format
            tool_choice="auto"
        )

        return {"messages": [response]}

    # -----------------------------------------------------
    # Should the graph continue to tools?
    # -----------------------------------------------------
    def _should_continue(self, state: AgentState) -> Literal["continue", "end"]:
        last_msg = state["messages"][-1]

        # Gemini tool calls come through last_msg.tool_calls
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "continue"

        return "end"

    # -----------------------------------------------------
    # Execute tool calls
    # -----------------------------------------------------
    def _execute_tools(self, state: AgentState):
        logger.info("Executing tools")

        last_msg = state["messages"][-1]
        tool_outputs = []

        for call in last_msg.tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            call_id = call["id"]

            logger.info("Executing tool", tool=tool_name, args=tool_args)

            try:
                tool = self.tools_by_name.get(tool_name)

                if not tool:
                    result = f"Tool '{tool_name}' not found."
                else:
                    result = tool.invoke(tool_args)

                tool_outputs.append(
                    ToolMessage(
                        content=str(result),
                        name=tool_name,
                        tool_call_id=call_id
                    )
                )

            except Exception as e:
                logger.error("Tool execution failed", error=str(e))
                tool_outputs.append(
                    ToolMessage(
                        content=f"Error executing {tool_name}: {str(e)}",
                        name=tool_name,
                        tool_call_id=call_id
                    )
                )

        return {"messages": tool_outputs}

    # -----------------------------------------------------
    # Public query method
    # -----------------------------------------------------
    async def query(self, query: str, namespace: str = "default", context=None):
        logger.info("Processing query", query=query, namespace=namespace)

        self.namespace = namespace

        state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "namespace": namespace
        }

        try:
            result = await self.graph.ainvoke(state)

            final = result["messages"][-1]
            text = final.content if hasattr(final, "content") else str(final)

            tools_used = len([m for m in result["messages"] if isinstance(m, ToolMessage)])

            return {
                "response": text,
                "analysis": {
                    "status": "completed",
                    "namespace": namespace,
                    "tools_used": tools_used
                },
                "suggestions": self._extract_suggestions(text),
                "success": True
            }

        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "response": f"Failure: {str(e)}",
                "analysis": {"status": "failed", "error": str(e)},
                "suggestions": ["Try specifying a namespace", "Check cluster connectivity"],
                "success": False
            }

    # -----------------------------------------------------
    # Suggestion extraction
    # -----------------------------------------------------
    def _extract_suggestions(self, text: str):
        result = []
        for line in text.split("\n"):
            if line.startswith("- ") and any(
                kw in line.lower() for kw in ["recommend", "should", "check", "try", "consider"]
            ):
                result.append(line[2:].strip())
        return result[:5]


# Global singleton
_agent_instance = None


def get_agent(kubeconfig_path=None):
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = KubernetesTroubleshootingAgent(kubeconfig_path)
    return _agent_instance
