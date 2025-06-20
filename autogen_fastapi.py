import asyncio
import logging
import os
import tempfile
import uuid
from typing import Dict, List, Optional

import boto3
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_core.models import ModelInfo

# Configure S3 client for kubeconfig retrieval
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
if not S3_BUCKET_NAME:
    raise ValueError("S3_BUCKET_NAME environment variable is not set.")

s3_client = boto3.client(
    "s3",
    region_name=os.environ.get("REGION", "us-west-2"),
    aws_access_key_id=os.environ.get("ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("SECRET_ACCESS_KEY"),
    endpoint_url=os.environ.get("S3_ENDPOINT")
)

async def download_kubeconfig(cluster_id: str) -> str:
    """Download kubeconfig file from S3 for the given cluster_id."""
    try:
        kubeconfig_key = f"kubeconfigs/{cluster_id}"
        temp_dir = tempfile.gettempdir()
        kubeconfig_path = os.path.join(temp_dir, f"{cluster_id}")
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)
        
        # Download the kubeconfig
        s3_client.download_file(S3_BUCKET_NAME, kubeconfig_key, kubeconfig_path)
        
        # Verify the file was downloaded
        if not os.path.exists(kubeconfig_path):
            raise FileNotFoundError(f"Kubeconfig file for cluster {cluster_id} not found in S3 after download.")
            
        # Set appropriate permissions
        os.chmod(kubeconfig_path, 0o600)
        
        return kubeconfig_path
    except Exception as e:
        logger.error(f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}"
        )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for conversation history
conversation_history: Dict[str, List[dict]] = {}

class QueryRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    cluster_id: Optional[str] = None

class QueryResponse(BaseModel):
    response: str
    session_id: str
    cluster_id: str

async def get_k8s_agent(cluster_id: str) -> AssistantAgent:
    """Dependency to provide a K8s agent for each request."""
    try:
        # First, download the kubeconfig
        kubeconfig_path = await download_kubeconfig(cluster_id)
        
        # Set up OpenAI model client
        model_client = OpenAIChatCompletionClient(
            model="gemini-2.0-flash",
            model_info=ModelInfo(
                vision=True,
                function_calling=True,
                json_output=True,
                family="unknown",
                structured_output=True
            ),
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
        
        # Configure MCP server for Kubernetes tools
        params = StdioServerParams(
            command="npx",
            args=["-y", "kubernetes-mcp-server@latest"],
            read_timeout_seconds=100,
            env={"KUBECONFIG": kubeconfig_path}
        )
        
        logger.info(f"Starting MCP server with kubeconfig: {kubeconfig_path}")
        
        try:
            # Get tools from the MCP server
            tools = await mcp_server_tools(params)
            logger.info("Successfully initialized MCP tools")
            
            # Create the K8s agent
            k8s_agent = AssistantAgent(
                "k8s_agent",
                description="An agent for k8s operations",
                tools=tools,
                model_client=model_client,
                system_message="""
                You are a k8s agent. You know how to interact with the Kubernetes API.
                
                Always prefer wide output format.
                
                If you don't have any explicit tasks left to complete, return TERMINATE.
                """,
            )
            
            return k8s_agent
            
        except Exception as e:
            logger.error(f"Error initializing MCP tools: {str(e)}")
            if hasattr(e, '__traceback__'):
                import traceback
                logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize MCP tools: {str(e)}. Please check the server logs for more details."
            )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to create K8s agent: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize K8s agent: {str(e)}. Please check the server logs for more details."
        )

@app.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    cluster_id: str = Query(..., description="The ID of the Kubernetes cluster"),
):
    """Handle incoming queries and route them to the K8s agent."""
    try:
        # Use cluster_id from query parameter if not provided in the request body
        cluster_id = request.cluster_id or cluster_id
        if not cluster_id:
            raise HTTPException(status_code=400, detail="cluster_id is required")
            
        # Get agent with the specified cluster_id
        agent = await get_k8s_agent(cluster_id)
        
        # Initialize session if new
        session_id = request.session_id or str(uuid.uuid4())
        if session_id not in conversation_history:
            conversation_history[session_id] = []
        
        # Add user message to history
        user_message = {"role": "user", "content": request.prompt}
        conversation_history[session_id].append(user_message)
        
        # Process the query with the agent
        task_result = await agent.run(task=request.prompt)
        
        # Extract the response text from the TaskResult
        response_text = ""
        if hasattr(task_result, 'messages') and task_result.messages:
            for msg in task_result.messages:
                if hasattr(msg, 'content'):
                    if isinstance(msg.content, str):
                        # Try to extract text from JSON content if possible
                        try:
                            content_data = json.loads(msg.content)
                            if isinstance(content_data, list):
                                for item in content_data:
                                    if isinstance(item, dict) and 'text' in item:
                                        response_text += item['text'] + "\n"
                            elif isinstance(content_data, dict) and 'text' in content_data:
                                response_text += content_data['text'] + "\n"
                        except (json.JSONDecodeError, AttributeError):
                            response_text += msg.content + "\n"
                    else:
                        response_text += str(msg.content) + "\n"
        
        # Add assistant response to history
        assistant_message = {"role": "assistant", "content": response_text}
        conversation_history[session_id].append(assistant_message)
        
        return QueryResponse(
            response=response_text,
            session_id=session_id,
            cluster_id=cluster_id
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

