from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal, Union, List, Dict, Any
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import logging
from fastapi import HTTPException
import json
from openai import OpenAI
import os
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

logger = logging.getLogger(__name__)

# Type aliases
ResourceType = Literal[
    'node', 'namespace', 'pod', 'container', 'statefulset', 'deployment', 'controller'
]

def parse_relative_date(date_str: str) -> date:
    """Parse relative date strings like 'today', 'yesterday', '3 days ago' into date objects."""
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

class DateRange(BaseModel):
    """Model representing a date range with validation."""
    model_config = ConfigDict(validate_by_name=True)

    start: date = Field(..., alias="from")
    to: date

    @field_validator("to")
    @classmethod
    def validate_range(cls, v, info):
        start = info.data.get("start")
        if start and v and start > v:
            raise ValueError("start date cannot be after end date")
        return v

    @classmethod
    def from_relative(cls, from_date: Union[str, date, None], to_date: Union[str, date, None]) -> 'DateRange':
        """Create a DateRange from relative or absolute date strings."""
        today = date.today()

        if isinstance(from_date, str):
            from_date = parse_relative_date(from_date)
        from_date = from_date or today

        if isinstance(to_date, str):
            to_date = parse_relative_date(to_date)
        to_date = to_date or today

        return cls(start=from_date, to=to_date)

class DashboardFilter(BaseModel):
    """Model for dashboard filters with resource type and date range."""
    model_config = ConfigDict(validate_by_name=True)

    selected_resource: Optional[ResourceType] = None
    date_range: DateRange

    @classmethod
    def from_query(cls, query: str) -> 'DashboardFilter':
        """Create a DashboardFilter from a natural language query."""
        from ..services.query_parser import parse_natural_language_query  # Using relative import
        
        try:
            parsed = parse_natural_language_query(query)
            return cls(
                selected_resource=parsed.get("resource_type"),
                date_range=DateRange.from_relative(
                    parsed.get("from_date"),
                    parsed.get("to_date")
                )
            )
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            # Return default filter with today's date range
            return cls(
                selected_resource=None,
                date_range=DateRange.from_relative("today", "today")
            )

# API Request/Response Models
class QueryRequest(BaseModel):
    """Request model for query endpoint."""
    prompt: str
    session_id: Optional[str] = None

class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    response: str
    session_id: Optional[str] = None  # Made optional with default None
    cluster_id: str

class FilterRequest(BaseModel):
    """Request model for filter endpoint."""
    query: str


class FilterResponse(BaseModel):
    """Response model for filter endpoint."""
    resource_type: Optional[str] = None
    from_date: date
    to_date: date

    @classmethod
    def from_relative(cls, from_date: Union[str, date, None], to_date: Union[str, date, None]) -> 'DateRange':
        today = date.today()

        if isinstance(from_date, str):
            logger.info(f"Parsing from_date string: {from_date}")
            from_date = parse_relative_date(from_date)
        elif from_date is None:
            logger.info("from_date is None, defaulting to today")
            from_date = today
        logger.info(f"Final from_date: {from_date}")

        if isinstance(to_date, str):
            logger.info(f"Parsing to_date string: {to_date}")
            to_date = parse_relative_date(to_date)
        elif to_date is None:
            logger.info("to_date is None, defaulting to today")
            to_date = today
        logger.info(f"Final to_date: {to_date}")

        return cls(start=from_date, to=to_date)

class DashboardFilter(BaseModel):
    model_config = ConfigDict(validate_by_name=True)

    selected_resource: Optional[ResourceType]
    date_range: DateRange

    @classmethod
    def from_query(cls, query: str) -> 'DashboardFilter':
        try:
            system_prompt = """You are a helpful assistant that extracts filter parameters from natural language queries.
            Extract the following information as JSON:
            - resource_type: One of [node, namespace, pod, container, statefulset, deployment, controller] or null
            - from_date: The start date in YYYY-MM-DD format or relative format like 'yesterday', '3 days ago'
            - to_date: The end date in YYYY-MM-DD format or relative format"""

            response = client.chat.completions.create(
                model="gemini-2.0-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            logger.info(f"Raw API response: {result}")

            resource = result.get("resource_type")
            from_date = result.get("from_date", "today")
            to_date = result.get("to_date", "today")

            logger.info(f"Before parsing - from_date: {from_date}, to_date: {to_date}")
            date_range = DateRange.from_relative(from_date, to_date)
            logger.info(f"After parsing - from_date: {date_range.start}, to_date: {date_range.to}")

            return cls(selected_resource=resource, date_range=date_range)

        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            raise HTTPException(status_code=400, detail=str(e))

# === API Models ===

class FilterResponse(BaseModel):
    resource_type: Optional[str]
    from_date: date
    to_date: date
