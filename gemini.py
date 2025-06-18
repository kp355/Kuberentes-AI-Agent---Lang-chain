import json
import os
from huggingface_hub import get_token
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List
import asyncio
from google import genai
from google.genai import types
from google.genai.chats import Chat

MODEL_ID = "gemini-2.0-flash-exp"

# System prompt that guides the LLM's behavior and capabilities
SYSTEM_PROMPT = """You are a helpful assistant capable of accessing external functions and engaging in casual chat. Use the responses from these function calls to provide accurate and informative answers. The answers should be natural and hide the fact that you are using tools to access real-time information. Guide the user about available tools and their capabilities. Always utilize tools to access real-time information when required. Engage in a friendly manner to enhance the chat experience.

# Tools

{tools}

# Notes 

- Ensure responses are based on the latest information available from function calls.
- Maintain an engaging, supportive, and friendly tone throughout the dialogue.
- Always highlight the potential of available tools to assist users comprehensively."""


# Initialize client using the API key from environment variable
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it and try again.")

# Configure the client with the API key
client = genai.Client()


class MCPClient:
    """
    A client class for interacting with the MCP (Model Control Protocol) server.
    This class manages the connection and communication with the SQLite database through MCP.
    """

    def __init__(self, server_params: StdioServerParameters):
        """Initialize the MCP client with server parameters"""
        self.server_params = server_params
        self.session = None
        self._client = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def connect(self):
        """Establishes connection to MCP server"""
        self._client = stdio_client(self.server_params)
        self.read, self.write = await self._client.__aenter__()
        session = ClientSession(self.read, self.write)
        self.session = await session.__aenter__()
        await self.session.initialize()

    async def get_available_tools(self) -> List[Any]:  
        """Retrieve a list of available tools from the MCP server."""  
        if not self.session:  
            raise RuntimeError("Not connected to MCP server")  
    
        # Get the tools from the session - this returns a ListToolsResult  
        tools_result = await self.session.list_tools()  
        return tools_result.tools

    def call_tool(self, tool_name: str) -> Any:
        """
        Create a callable function for a specific tool.
        This allows us to execute database operations through the MCP server.

        Args:
            tool_name: The name of the tool to create a callable for

        Returns:
            A callable async function that executes the specified tool
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        async def callable(*args, **kwargs):
            response = await self.session.call_tool(tool_name, arguments=kwargs)
            return response.content[0].text

        return callable


async def agent_loop(query: str, tools: dict, messages: List[types.Content] = None):  
    # Convert tools to Gemini function declarations format  
    tool_declarations = []  
    for tool_name, tool in tools.items():  
        # Convert parameter types to Gemini compatible types  
        parsed_parameters = {}  
        required_params = []  
          
        if 'properties' in tool.get('parameters', {}):  
            parsed_parameters = tool['parameters']['properties'].copy()  
            required_params = tool.get('parameters', {}).get('required', [])  
              
        # Create function declaration with proper structure  
        declaration = types.FunctionDeclaration(  
            name=tool_name,  
            description=tool.get('description', ''),  
            parameters=types.Schema(  
                type=types.Type.OBJECT,  
                properties={  
                    key: types.Schema(  
                        type=types.Type.STRING,  # Adjust based on actual parameter types  
                        description=value.get('description', '')  
                    ) for key, value in parsed_parameters.items()  
                },  
                required=required_params  
            ),  
        )  
        tool_declarations.append(declaration)  
  
    # Initialize chat with system instruction  
    generation_config = types.GenerateContentConfig(  
        system_instruction=SYSTEM_PROMPT.format(  
            tools="\n- ".join([  
                f"{name}: {tool['description']}"  
                for name, tool in tools.items()  
            ])  
        ),  
        temperature=0,  
        tools=[types.Tool(function_declarations=tool_declarations)] if tool_declarations else [],  
    )  
    contents = [] if messages is None else messages # check if there is a previous conversation
    contents.append(types.Content(role="user", parts=[types.Part(text=query)])) # add the user query to the contents
    # Send query and get response
    response = client.models.generate_content(
        model=MODEL_ID,
        config=generation_config,
        contents=contents,
    )
    # Handle tool calls if present
    for part in response.candidates[0].content.parts:
        contents.append(types.Content(role="model", parts=[part]))
        if part.function_call:
            function_call = part.function_call
            # add the function call to the contents
            # Call the tool with arguments
            tool_result = await tools[function_call.name]["callable"](
                **function_call.args
            )
            # Build the response parts.
            function_response_part = types.Part.from_function_response(
                name=function_call.name,
                response={"result": tool_result},
            )
            contents.append(types.Content(role="user", parts=[function_response_part]))
            # Send follow-up with tool results
            func_gen_response = client.models.generate_content(
                model=MODEL_ID, config=generation_config, contents=contents
            )
            contents.append(types.Content(role="model", parts=[func_gen_response]))
    return contents


async def main():
    """
    Main function that sets up the MCP server, initializes tools, and runs the interactive loop.
    The server is run in a Docker container to ensure isolation and consistency.
    """
    # Configure Docker-based MCP server for SQLite
    server_params = StdioServerParameters(
        command="npx",
        args=[
            "-y", "kubernetes-mcp-server@latest",
        ],
        env=None,
    )

    # Start MCP client and create interactive session
    async with MCPClient(server_params) as mcp_client:
        # Get available database tools and prepare them for the LLM
        mcp_tools = await mcp_client.get_available_tools()
        # Convert MCP tools into a format the LLM can understand and use
        tools = {}
        for tool in mcp_tools:
            # Handle both tuple and object formats
            if isinstance(tool, tuple):
                # If tool is a tuple, assume it's in the format (name, description, inputSchema)
                if len(tool) >= 3:
                    tool_name, tool_desc, tool_schema = tool[0], tool[1], tool[2]
                else:
                    continue  # Skip invalid tool format
            else:
                # Handle object format with attributes
                tool_name = getattr(tool, 'name', None)
                tool_desc = getattr(tool, 'description', '')
                tool_schema = getattr(tool, 'inputSchema', {})
            
            if tool_name and tool_name != "list_tables":
                # Store tool metadata and callable
                tools[tool_name] = {
                    "name": tool_name,
                    "description": tool_desc,
                    "parameters": tool_schema,
                    "callable": mcp_client.call_tool(tool_name)
                }

        # Start interactive prompt loop for user queries
        messages = None
        while True:
            try:
                # Get user input and check for exit commands
                user_input = input("\nEnter your prompt (or 'quit' to exit): ")
                if user_input.lower() in ["quit", "exit", "q"]:
                    break
                # Process the prompt and run agent loop
                messages = await agent_loop(user_input, tools, messages)
                # Find the last model message with text and print it
                for message in reversed(messages):
                    if message.role == "model" and any(
                        part.text for part in message.parts
                    ):
                        for part in message.parts:
                            if part.text is not None and part.text.strip() != "":
                                print(f"Assistant: {part.text}")
                                break
                        break
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"\nError occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())