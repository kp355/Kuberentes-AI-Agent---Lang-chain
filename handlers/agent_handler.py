import json
import logging
import traceback
import re
from fastapi import APIRouter, HTTPException, Query
from models.model import QueryRequest, QueryResponse
from utils.utils import get_k8s_agent
from utils.utils import download_kubeconfig
from autogen_ext.tools.mcp import McpWorkbench
from autogen_ext.tools.mcp import StdioServerParams

router = APIRouter()
logger = logging.getLogger(__name__)

def _extract_text(content):
    if not content:
        return ""
    # If it's a list, extract recursively
    if isinstance(content, list):
        return "\n".join(_extract_text(item) for item in content)
    # If it's a dict, extract "text" or recurse
    if isinstance(content, dict):
        if "text" in content:
            return _extract_text(content["text"])
        return "\n".join(_extract_text(v) for v in content.values())
    # Now it's a string
    content = str(content)
    # Remove FunctionCall lines
    content = re.sub(r"FunctionCall\(.*?\)\n?", "", content, flags=re.DOTALL)
    # Remove the prompt (assumes prompt is before first '[')
    content = re.sub(r"^.*?\[", "[", content, flags=re.DOTALL)
    # Find all JSON objects or arrays in the string
    json_candidates = re.findall(r'(\{.*\}|\[.*\])', content, flags=re.DOTALL)
    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate)
            extracted = _extract_text(parsed)
            if extracted.strip():
                return extracted.strip()
        except Exception:
            continue
    # If nothing found, try to extract content='...'
    content_match = re.search(r"content=['\"](.+?)['\"]", content, re.DOTALL)
    if content_match:
        inner = content_match.group(1)
        try:
            parsed = json.loads(inner)
            return _extract_text(parsed)
        except Exception:
            return inner.replace("\\n", "\n").replace("\\\\n", "\n").replace("\\", "")
    # Final fallback: replace escaped newlines
    content = content.replace("\\n", "\n").replace("\\\\n", "\n").replace("\\", "")
    return content.strip()

def remove_prompt(text):
    """
    Removes the first line (assumed to be the prompt) from the text.
    """
    lines = text.strip().splitlines()
    if len(lines) > 1:
        return "\n".join(lines[1:]).lstrip()
    else:
        return text.strip()

@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    cluster_id: str = Query(..., description="The ID of the Kubernetes cluster"),
):
    try:
        prompt_text = request.prompt.strip().lower()
        # if "analyze" in prompt_text:
        #     kubeconfig = await download_kubeconfig(cluster_id)

        #     # ✅ Step 2: Build k8sgpt analyze command
        #     process = await asyncio.create_subprocess_exec(
        #         "k8sgpt", "analyze",
        #         "--kubeconfig", kubeconfig,
        #         "--output", "json",  # return machine-readable format
        #         stdout=asyncio.subprocess.PIPE,
        #         stderr=asyncio.subprocess.PIPE
        #     )

        #     # ✅ Step 3: Wait and capture output
        #     stdout, stderr = await process.communicate()

        #     if process.returncode != 0:
        #         raise Exception(f"[k8sgpt error] {stderr.decode().strip()}")

        #     return QueryResponse(
        #         response=stdout.decode().strip(),
        #         cluster_id=cluster_id
        #     )
        

       
        # ✅ Default case: Use your get_k8s_agent
        agent = await get_k8s_agent(cluster_id)
        task_result = await agent.run(task=request.prompt)

        response_parts = []
        if hasattr(task_result, "messages"):
            for msg in task_result.messages:
                if hasattr(msg, "content"):
                    response_parts.append(_extract_text(msg.content))

        # Remove the prompt from the cleaned response
        cleaned_response = remove_prompt("\n".join(response_parts).strip())

        return QueryResponse(
            response=cleaned_response,
            cluster_id=cluster_id
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))
   




import asyncio
from fastapi import APIRouter, HTTPException, Query
from models.model import QueryRequest, QueryResponse
from utils.utils import download_kubeconfig

router = APIRouter()

@router.post("/analyze", response_model=QueryResponse)
async def analyze_with_k8sgpt(
    request: QueryRequest,
    cluster_id: str = Query(..., description="Kubernetes cluster ID"),
):
    try:
        # ✅ Step 1: Get kubeconfig path
        kubeconfig = await download_kubeconfig(cluster_id)

        # ✅ Step 2: Build k8sgpt analyze command
        process = await asyncio.create_subprocess_exec(
            "k8sgpt", "analyze",
            "--kubeconfig", kubeconfig,
            "--output", "json",  # return machine-readable format
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # ✅ Step 3: Wait and capture output
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"[k8sgpt error] {stderr.decode().strip()}")

        return QueryResponse(
            response=stdout.decode().strip(),
            cluster_id=cluster_id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"K8sGPT failed: {str(e)}")
