import json
import os
import boto3
from fastapi import FastAPI, HTTPException, Response, Depends, Query
from pydantic import BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, Dict, List
import asyncio
from google import genai
from google.genai import types
import uuid
from datetime import datetime
import tempfile
import logging
from fastapi.middleware.cors import CORSMiddleware

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

MODEL_ID = "gemini-2.0-flash-exp"

SYSTEM_PROMPT = """You are a helpful assistant capable of accessing external functions and engaging in casual chat. Use the responses from these function calls to provide accurate and informative answers. The answers should be natural and hide the fact that you are using tools to access real-time information. Guide the user about available tools and their capabilities. Always utilize tools to access real-time information when required. Engage in a friendly manner to enhance the chat experience.

# Tools

{tools}

# Notes 

- Ensure responses are based on the latest information available from function calls.
- Maintain an engaging, supportive, and friendly tone throughout the dialogue.
- Always highlight the potential of available tools to assist users comprehensively."""

# Initialize clients
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
client = genai.Client()

S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
if not S3_BUCKET_NAME:
    raise ValueError("S3_BUCKET_NAME environment variable is not set.")
s3_client = boto3.client(
    "s3",
    region_name=os.environ.get("REGION"),
    aws_access_key_id=os.environ.get("ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("SECRET_ACCESS_KEY"),
    endpoint_url=os.environ.get("S3_ENDPOINT")
)

# In-memory storage for conversation history
conversation_history: Dict[str, List[types.Content]] = {}

async def download_kubeconfig(cluster_id: str) -> str:
    """Download kubeconfig file from S3 for the given cluster_id."""
    try:
        kubeconfig_key = f"kubeconfigs/{cluster_id}"
        temp_dir = tempfile.gettempdir()
        kubeconfig_path = os.path.join(temp_dir, f"{cluster_id}")
        s3_client.download_file(S3_BUCKET_NAME, kubeconfig_key, kubeconfig_path)
        if not os.path.exists(kubeconfig_path):
            raise ValueError(f"Kubeconfig file for cluster {cluster_id} not found in S3.")
        return kubeconfig_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}")

class MCPClient:
    def __init__(self, server_params: StdioServerParameters):
        self.server_params = server_params
        self.session = None
        self._client = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def connect(self):
        self._client = stdio_client(self.server_params)
        self.read, self.write = await self._client.__aenter__()
        session = ClientSession(self.read, self.write)
        self.session = await session.__aenter__()
        await self.session.initialize()

    async def get_available_tools(self) -> List[Any]:
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        tools_result = await self.session.list_tools()
        return tools_result.tools

    def call_tool(self, tool_name: str) -> Any:
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        async def callable(*args, **kwargs):
            response = await self.session.call_tool(tool_name, arguments=kwargs)
            return response.content[0].text
        return callable

async def get_mcp_client(cluster_id: str) -> MCPClient:
    """Dependency to provide MCPClient for each request."""
    kubeconfig_path = await download_kubeconfig(cluster_id)
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "kubernetes-mcp-server@latest"],
        env={"KUBECONFIG": kubeconfig_path},
    )
    mcp_client = MCPClient(server_params)
    await mcp_client.__aenter__()
    try:
        yield mcp_client
    finally:
        await mcp_client.__aexit__(None, None, None)

async def agent_loop(query: str, tools: dict, messages: List[types.Content] = None, session_id: str = None):
    tool_declarations = []
    for tool_name, tool in tools.items():
        parsed_parameters = {}
        required_params = []
        if 'properties' in tool.get('parameters', {}):
            parsed_parameters = tool['parameters']['properties'].copy()
            required_params = tool.get('parameters', {}).get('required', [])
        declaration = types.FunctionDeclaration(
            name=tool_name,
            description=tool.get('description', ''),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    key: types.Schema(
                        type=types.Type.STRING,
                        description=value.get('description', '')
                    ) for key, value in parsed_parameters.items()
                },
                required=required_params
            ),
        )
        tool_declarations.append(declaration)

    generation_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(
            tools="\n- ".join([f"{name}: {tool['description']}" for name, tool in tools.items()])
        ),
        temperature=0,
        tools=[types.Tool(function_declarations=tool_declarations)] if tool_declarations else [],
    )
    contents = [] if messages is None else messages
    contents.append(types.Content(role="user", parts=[types.Part(text=query)]))

    response = client.models.generate_content(
        model=MODEL_ID,
        config=generation_config,
        contents=contents,
    )

    for part in response.candidates[0].content.parts:
        contents.append(types.Content(role="model", parts=[part]))
        if part.function_call:
            function_call = part.function_call
            tool_result = await tools[function_call.name]["callable"](**function_call.args)
            function_response_part = types.Part.from_function_response(
                name=function_call.name,
                response={"result": tool_result},
            )
            contents.append(types.Content(role="user", parts=[function_response_part]))
            func_gen_response = client.models.generate_content(
                model=MODEL_ID, config=generation_config, contents=contents
            )
            contents.append(types.Content(role="model", parts=[func_gen_response]))
    return contents

class QueryRequest(BaseModel):
    prompt: str
    session_id: str = None
    cluster_id: str = None  # Optional in body since we'll get it from query params

class QueryResponse(BaseModel):
    response: str
    session_id: str
    cluster_id: str

@app.options("/query")
async def handle_options():
    logger.info("Handling OPTIONS request for /query")
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@app.post("/query")
async def handle_query(
    request: QueryRequest, 
    cluster_id: str = Query(..., alias="cluster_id"),
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    logger.info(f"Received query: {request.prompt}, session ID: {request.session_id}, cluster ID: {request.cluster_id}")
    try:
        session_id = request.session_id or str(uuid.uuid4())
        # Use cluster_id from query parameters (which is passed to get_mcp_client)

        # Get available database tools
        mcp_tools = await mcp_client.get_available_tools()
        tools = {}
        for tool in mcp_tools:
            if isinstance(tool, tuple):
                if len(tool) >= 3:
                    tool_name, tool_desc, tool_schema = tool[0], tool[1], tool[2]
                else:
                    continue
            else:
                tool_name = getattr(tool, 'name', None)
                tool_desc = getattr(tool, 'description', '')
                tool_schema = getattr(tool, 'inputSchema', {})
                
            if tool_name and tool_name != "list_tables":
                tools[tool_name] = {
                    "name": tool_name,
                    "description": tool_desc,
                    "parameters": tool_schema,
                    "callable": mcp_client.call_tool(tool_name)
                }

        # Get existing conversation history or initialize new
        messages = conversation_history.get(session_id, [])

        # Process the query
        messages = await agent_loop(request.prompt, tools, messages, session_id)

        # Store updated conversation history
        conversation_history[session_id] = messages

        # Find the last model message with text
        response_text = ""
        for message in reversed(messages):
            if message.role == "model" and any(part.text for part in message.parts):
                for part in message.parts:
                    if part.text is not None and part.text.strip() != "":
                        response_text = part.text
                        break
                break

        return QueryResponse(response=response_text, session_id=session_id, cluster_id=cluster_id)

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup")
    # No global MCP client initialization needed

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown")
    # No global MCP client cleanup needed