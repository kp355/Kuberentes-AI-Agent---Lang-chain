"""LangGraph-based Kubernetes troubleshooting agent."""
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, FunctionMessage
from langchain_core.agents import AgentAction, AgentFinish
from models.ai import get_llm
from models.prompt import get_troubleshooting_prompt
from core.k8s_tools import get_k8s_tools
import structlog
import operator

logger = structlog.get_logger()


class AgentState(TypedDict):
    """State for the LangGraph agent."""
    messages: Annotated[List[BaseMessage], operator.add]
    query: str
    namespace: str
    context: Dict[str, Any]
    analysis: Dict[str, Any]
    suggestions: List[str]
    next: str


class KubernetesTroubleshootingAgent:
    """LangGraph agent for Kubernetes troubleshooting."""
    
    def __init__(self, kubeconfig_path: str = None):
        """Initialize the agent with LangGraph workflow."""
        self.llm = get_llm()
        self.tools = get_k8s_tools(kubeconfig_path)
        self.tool_executor = ToolExecutor(self.tools)
        
        # Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Build the graph
        self.graph = self._build_graph()
        logger.info("LangGraph agent initialized")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("analyze_query", self._analyze_query)
        workflow.add_node("select_tools", self._select_tools)
        workflow.add_node("execute_tools", self._execute_tools)
        workflow.add_node("synthesize_response", self._synthesize_response)
        
        # Add edges
        workflow.set_entry_point("analyze_query")
        workflow.add_edge("analyze_query", "select_tools")
        workflow.add_conditional_edges(
            "select_tools",
            self._should_continue,
            {
                "continue": "execute_tools",
                "end": "synthesize_response"
            }
        )
        workflow.add_edge("execute_tools", "select_tools")
        workflow.add_edge("synthesize_response", END)
        
        return workflow.compile()
    
    def _analyze_query(self, state: AgentState) -> AgentState:
        """Analyze the user query and determine intent."""
        logger.info("Analyzing query", query=state["query"])
        
        # Add context about available tools
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools
        ])
        
        context_message = f"""Available Kubernetes tools:
{tool_descriptions}

Analyze the query and determine which tools to use."""
        
        state["context"]["tool_descriptions"] = tool_descriptions
        state["messages"].append(HumanMessage(content=context_message))
        
        return state
    
    def _select_tools(self, state: AgentState) -> AgentState:
        """Select which tools to use based on the query."""
        logger.info("Selecting tools")
        
        messages = state["messages"]
        
        # Get LLM response with tool calls
        response = self.llm_with_tools.invoke(messages)
        state["messages"].append(response)
        
        return state
    
    def _should_continue(self, state: AgentState) -> str:
        """Determine if we should continue with tool execution or synthesize response."""
        last_message = state["messages"][-1]
        
        # If the LLM makes a tool call, continue
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "continue"
        
        # Otherwise, we're done with tool execution
        return "end"
    
    def _execute_tools(self, state: AgentState) -> AgentState:
        """Execute the selected tools."""
        logger.info("Executing tools")
        
        last_message = state["messages"][-1]
        
        # Execute all tool calls
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            logger.info("Executing tool", tool=tool_name, args=tool_args)
            
            # Execute the tool
            action = AgentAction(
                tool=tool_name,
                tool_input=tool_args,
                log=f"Calling {tool_name} with {tool_args}"
            )
            
            try:
                result = self.tool_executor.invoke(action)
                
                # Add tool result to messages
                state["messages"].append(
                    FunctionMessage(
                        content=str(result),
                        name=tool_name
                    )
                )
                
                logger.info("Tool executed successfully", tool=tool_name)
                
            except Exception as e:
                logger.error("Tool execution failed", tool=tool_name, error=str(e))
                state["messages"].append(
                    FunctionMessage(
                        content=f"Error executing {tool_name}: {str(e)}",
                        name=tool_name
                    )
                )
        
        return state
    
    def _synthesize_response(self, state: AgentState) -> AgentState:
        """Synthesize final response from gathered information."""
        logger.info("Synthesizing response")
        
        # Create final prompt with all gathered context
        final_prompt = f"""Based on the Kubernetes information gathered, provide a comprehensive response to:

Query: {state['query']}
Namespace: {state['namespace']}

Provide:
1. Root cause analysis (if applicable)
2. Clear explanation of findings
3. Actionable remediation steps
4. Prevention recommendations

Be specific, concise, and helpful."""
        
        state["messages"].append(HumanMessage(content=final_prompt))
        
        # Get final response
        final_response = self.llm.invoke(state["messages"])
        state["messages"].append(final_response)
        
        # Extract suggestions from the response
        state["analysis"] = {
            "status": "completed",
            "tools_used": len([m for m in state["messages"] if isinstance(m, FunctionMessage)])
        }
        
        return state
    
    async def query(self, query: str, namespace: str = "default", context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a troubleshooting query."""
        logger.info("Processing query", query=query, namespace=namespace)
        
        # Initialize state
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "query": query,
            "namespace": namespace,
            "context": context or {},
            "analysis": {},
            "suggestions": [],
            "next": ""
        }
        
        try:
            # Run the graph
            result = await self.graph.ainvoke(initial_state)
            
            # Extract final response
            final_message = result["messages"][-1]
            response_text = final_message.content if hasattr(final_message, 'content') else str(final_message)
            
            return {
                "response": response_text,
                "analysis": result["analysis"],
                "suggestions": result["suggestions"],
                "success": True
            }
            
        except Exception as e:
            logger.error("Agent execution failed", error=str(e))
            return {
                "response": f"Error processing query: {str(e)}",
                "analysis": {"status": "failed", "error": str(e)},
                "suggestions": [],
                "success": False
            }


# Global agent instance
_agent_instance = None


def get_agent(kubeconfig_path: str = None) -> KubernetesTroubleshootingAgent:
    """Get or create the global agent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = KubernetesTroubleshootingAgent(kubeconfig_path)
    return _agent_instance
