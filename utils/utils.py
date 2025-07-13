import os
import tempfile
import boto3
from fastapi import HTTPException
from datetime import date, datetime, timedelta
import logging
import yaml
# Configure logging



from autogen_agentchat.agents import AssistantAgent

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_core.models import ModelInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        try:
            # Get tools from the MCP server
            tools = await mcp_server_tools(params)
            
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

def validate_kubeconfig_yaml(file_path: str):
    """Check that the kubeconfig is valid YAML."""
    try:
        with open(file_path, "r") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Kubeconfig YAML is invalid: {e}"
        )

# async def download_kubeconfig(cluster_id: str) -> str:
#     """
#     Get kubeconfig file path, download from S3 if not already present.
    
#     Args:
#         cluster_id: The ID of the Kubernetes cluster
        
#     Returns:
#         str: Path to the kubeconfig file
#     """
#     try:
#         kubeconfig_key = f"kubeconfigs/{cluster_id}"
#         temp_dir = tempfile.gettempdir()
#         kubeconfig_path = os.path.join(temp_dir, f"{cluster_id}")
        
#         # Return existing kubeconfig if it's already downloaded and valid
#         if os.path.exists(kubeconfig_path):
#             logger.info(f"Using existing kubeconfig at {kubeconfig_path}")
#             return kubeconfig_path
            
#         logger.info(f"Downloading kubeconfig for cluster {cluster_id}...")
        
#         # Ensure the directory exists
#         os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)
        
#         # Download the kubeconfig
#         s3_client = get_s3_client()
#         s3_client.download_file(S3_BUCKET_NAME, kubeconfig_key, kubeconfig_path)
        
#         # Verify the file was downloaded
#         if not os.path.exists(kubeconfig_path):
#             raise FileNotFoundError(f"Kubeconfig file for cluster {cluster_id} not found in S3 after download.")
            
#         # Set appropriate permissions
#         os.chmod(kubeconfig_path, 0o600)
        
#         logger.info(f"Successfully downloaded kubeconfig to {kubeconfig_path}")
#         return kubeconfig_path
#     except Exception as e:
#         logger.error(f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}"
#         )

async def download_kubeconfig(cluster_id: str) -> str:
    """
    Download kubeconfig from S3 or use existing file if present and valid.

    Args:
        cluster_id: The ID of the Kubernetes cluster

    Returns:
        str: Path to the kubeconfig file
    """
    try:
        kubeconfig_key = f"kubeconfigs/{cluster_id}"
        temp_dir = tempfile.gettempdir()
        kubeconfig_path = os.path.join(temp_dir, f"{cluster_id}")

        # Check if file exists and is valid
        if os.path.exists(kubeconfig_path):
            logger.info(f"Using existing kubeconfig at {kubeconfig_path}")
            try:
                validate_kubeconfig_yaml(kubeconfig_path)
                return kubeconfig_path
            except HTTPException as ve:
                logger.warning(f"Existing kubeconfig invalid. Re-downloading: {ve.detail}")

        logger.info(f"Downloading kubeconfig for cluster {cluster_id}...")

        # Ensure temp dir exists
        os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)

        # Download file
        s3_client = get_s3_client()
        s3_client.download_file(S3_BUCKET_NAME, kubeconfig_key, kubeconfig_path)

        # Validate downloaded file
        validate_kubeconfig_yaml(kubeconfig_path)

        # Set permissions
        os.chmod(kubeconfig_path, 0o600)
        logger.info(f"Successfully downloaded kubeconfig to {kubeconfig_path}")
        return kubeconfig_path

    except Exception as e:
        logger.error(f"❌ Failed to download kubeconfig for cluster {cluster_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download kubeconfig for cluster {cluster_id}: {str(e)}"
        )

# Configure S3 client for kubeconfig retrieval
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
if not S3_BUCKET_NAME:
    raise ValueError("S3_BUCKET_NAME environment variable is not set.")


def get_s3_client():
    s3_client = boto3.client(
    "s3",
    region_name=os.environ.get("REGION", "us-west-2"),
    aws_access_key_id=os.environ.get("ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("SECRET_ACCESS_KEY"),
    endpoint_url=os.environ.get("S3_ENDPOINT")
)
    
    return s3_client    

def parse_relative_date(date_str: str) -> date:
    today = date.today()
    date_str = date_str.lower().strip()

    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        pass

    if date_str == 'today':
        return today
    elif date_str == 'yesterday':
        return today - timedelta(days=1)
    elif date_str == 'tomorrow':
        return today + timedelta(days=1)

    match = re.match(r'(\d+)\s+(day|week|month|year)s?\s+ago', date_str)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit == 'day':
            return today - timedelta(days=num)
        elif unit == 'week':
            return today - timedelta(weeks=num)
        elif unit == 'month':
            return today - relativedelta(months=num)
        elif unit == 'year':
            return today - relativedelta(years=num)

    logger.warning(f"Could not parse date string '{date_str}', falling back to today")
    return today
