import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, List, Dict
import asyncio
from openai import OpenAI, AsyncOpenAI

# --- Configuration ---
OPENAI_COMPATIBLE_GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it and try again.")

# Initialize OpenAI client pointing to Gemini's compatibility endpoint
client = AsyncOpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# System prompt
SYSTEM_PROMPT = """You are a helpful assistant capable of accessing external functions and engaging in casual chat. Use the responses from these function calls to provide accurate and informative answers. The answers should be natural and hide the fact that you are using tools to access real-time information. Guide the user about available tools and their capabilities. Always utilize tools to access real-time information when required. Engage in a friendly manner to enhance the chat experience.

# Tools

{tools}

# Notes 

- Ensure responses are based on the latest information available from function calls.
- Maintain an engaging, supportive, and friendly tone throughout the dialogue.
- Always highlight the potential of available tools to assist users comprehensively."""


# --- MCP Client Class ---
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
            if response.content and len(response.content) > 0 and hasattr(response.content[0], 'text'):
                return response.content[0].text
            return str(response.content)
        return callable


async def agent_loop(query: str, tools: dict, messages: List[dict] = None):
    print("running agent loop")
    for tool in tools.values():
        print(tool['name'])
        print(tool['schema']['function']['description'])
    messages = (
        [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    tools="\n- ".join(
                        [
                            f"{t['name']}: {t['schema']['function']['description']}"
                            for t in tools.values()
                        ]
                    )
                ),  # Creates System prompt based on available MCP server tools
            },
        ]
        if messages is None
        else messages  # reuse existing messages if provided
    )
    # add user query to the messages list
    messages.append({"role": "user", "content": query})


    print("going to first response")

    # Query LLM with the system prompt, user query, and available tools
    first_response = await client.chat.completions.create(
          model="gemini-2.0-flash",
        messages=messages,
        tools=([t["schema"] for t in tools.values()] if len(tools) > 0 else None),
        max_tokens=4096,
          tool_choice="auto",
        temperature=0,
    )
    print("first response", first_response)
    # detect how the LLM call was completed:
    # tool_calls: if the LLM used a tool
    print("tool calls are", first_response.choices[0].message.tool_calls)
    # stop: If the LLM generated a general response, e.g. "Hello, how can I help you today?"
    stop_reason = (
        "tool_calls"
        if first_response.choices[0].message.tool_calls is not None
        else first_response.choices[0].finish_reason
    )
    print("stop reason is", stop_reason)

    if stop_reason == "tool_calls":
        # Extract tool use details from response
        for tool_call in first_response.choices[0].message.tool_calls:
            arguments = (
                json.loads(tool_call.function.arguments)
                if isinstance(tool_call.function.arguments, str)
                else tool_call.function.arguments
            )
            try:
                # Call the tool with the arguments using our callable initialized in the tools dict
                tool_result = await tools[tool_call.function.name]["callable"](**arguments)
                print(f"Tool {tool_call.function.name} executed successfully")
                print("Tool result type:", type(tool_result))
                print("Tool result content:", tool_result)
            except Exception as e:
                error_msg = f"Error calling tool {tool_call.function.name}: {str(e)}"
                print(error_msg)
                tool_result = {"error": error_msg}
            # Add the tool result to the messages list
            tool_response = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,  # Make sure this matches the function name exactly
                "content": json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result,
            }
            print("Tool response:", json.dumps(tool_response, indent=2))
            messages.append(tool_response)
        print("messages are", messages)
        try:
            # Ensure messages are in the correct format
            formatted_messages = []
            for msg in messages:
                # Skip any None or empty messages
                if not msg:
                    continue
                # Ensure each message has the required fields
                formatted_msg = {
                    "role": msg.get("role"),
                    "content": msg.get("content", ""),
                }
                # Add tool_call_id if present
                if "tool_call_id" in msg:
                    formatted_msg["tool_call_id"] = msg["tool_call_id"]
                # Add name if present
                if "name" in msg:
                    formatted_msg["name"] = msg["name"]
                formatted_messages.append(formatted_msg)

            print("Sending to Gemini with messages:", json.dumps(formatted_messages, indent=2))
            
            # Query LLM with the user query and the tool results
            new_response = await client.chat.completions.create(
                model=OPENAI_COMPATIBLE_GEMINI_MODEL,
                messages=formatted_messages,
                tools=([t["schema"] for t in tools.values()] if tools else None),
                max_tokens=4096,
                tool_choice="auto",
                temperature=0,
            )
            print("Received response from Gemini")
        except Exception as e:
            print(f"Error calling Gemini API: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print("Response content:", e.response.text)
            raise
        print("new response", new_response)

    elif stop_reason == "stop":
        # If the LLM stopped on its own, use the first response
        new_response = first_response

    else:
        raise ValueError(f"Unknown stop reason: {stop_reason}")

    # Add the LLM response to the messages list
    messages.append(
        {"role": "assistant", "content": new_response.choices[0].message.content}
    )

    # Return the LLM response and messages
    print("messages are",messages)
    return new_response.choices[0].message.content, messages

# --- Main Function ---
async def main():
    # Configure Kubernetes MCP server
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "kubernetes-mcp-server@latest"],
        env=None,
    )

    async with MCPClient(server_params) as mcp_client:
        try:
            # Get available tools
            mcp_tools = await mcp_client.get_available_tools()
            print("Raw MCP tools:", mcp_tools)  # Debug: Inspect raw tools

            # Convert MCP tools to OpenAI-compatible format
            tools = {}
            for tool in mcp_tools:
                try:
                    if isinstance(tool, tuple):
                        if len(tool) >= 3:
                            tool_name, tool_desc, tool_schema = tool[0], tool[1], tool[2]
                        else:
                            print(f"Skipping invalid tool tuple: {tool}")
                            continue
                    else:
                        tool_name = getattr(tool, 'name', None)
                        tool_desc = getattr(tool, 'description', '')
                        tool_schema = getattr(tool, 'inputSchema', {})

                    if not tool_name or tool_name == "list_tables":
                        continue
                        
                    # Ensure the schema has the required structure
                    if not isinstance(tool_schema, dict):
                        tool_schema = {}
                    if 'type' not in tool_schema:
                        tool_schema['type'] = 'object'
                    if 'properties' not in tool_schema:
                        tool_schema['properties'] = {}
                    if 'required' not in tool_schema:
                        tool_schema['required'] = []

                    tools[tool_name] = {
                        "name": tool_name,
                        "callable": mcp_client.call_tool(tool_name),
                        "schema": {
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "description": tool_desc or f"Tool: {tool_name}",
                                "parameters": tool_schema
                            }
                        }
                    }
                    print(f"Registered tool: {tool_name}")
                except Exception as e:
                    print(f"Error processing tool {tool if isinstance(tool, str) else tool.__class__.__name__}: {e}")
                    continue

            print("Constructed tools:", json.dumps([t["schema"] for t in tools.values()], indent=2))  # Debug: Inspect tool schema

            # Interactive prompt loop
            messages = None
            while True:
                try:
                    user_input = input("\nEnter your prompt (or 'quit' to exit): ")
                    if user_input.lower() in ["quit", "exit", "q"]:
                        break

                    response, messages = await agent_loop(user_input, tools, messages)
                    if response:
                        print(f"\nAssistant: {response}")
                    else:
                        print("\nNo response received from the assistant.")
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"\nError occurred: {e}")
        except Exception as e:
            print(f"Error initializing MCP client or tools: {e}")

if __name__ == "__main__":
    asyncio.run(main())