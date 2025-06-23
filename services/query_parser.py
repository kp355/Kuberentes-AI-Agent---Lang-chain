import json
import logging
from typing import Dict, Any
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta"
)

def parse_natural_language_query(query: str) -> Dict[str, Any]:
    """
    Parse a natural language query into structured data using OpenAI.
    
    Args:
        query: Natural language query string
        
    Returns:
        Dict containing parsed parameters (resource_type, from_date, to_date)
    """
    system_prompt = """You are a helpful assistant that extracts filter parameters from natural language queries.
    Extract the following information as JSON:
    - resource_type: One of [node, namespace, pod, container, statefulset, deployment, controller] or null
    - from_date: The start date in YYYY-MM-DD format or relative format like 'yesterday', '3 days ago'
    - to_date: The end date in YYYY-MM-DD format or relative format like 'today', '1 week from now'"""
    
    try:
        response = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        logger.info(f"Parsed query result: {result}")
        
        # Ensure we have all required fields with defaults
        return {
            "resource_type": result.get("resource_type"),
            "from_date": result.get("from_date", "today"),
            "to_date": result.get("to_date", "today")
        }
        
    except Exception as e:
        logger.error(f"Error parsing query with OpenAI: {e}")
        # Return default values on error
        return {
            "resource_type": None,
            "from_date": "today",
            "to_date": "today"
        }
