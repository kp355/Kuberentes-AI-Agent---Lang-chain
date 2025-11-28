"""Natural language query parser using LangChain."""
from langchain_core.output_parsers import JsonOutputParser
from models.ai import get_llm
from models.prompt import get_filter_parsing_prompt
from models.model import DashboardFilter, FilterResponse
import structlog
import json

logger = structlog.get_logger()


class QueryParserService:
    """Service for parsing natural language queries into structured filters."""
    
    def __init__(self):
        self.llm = get_llm()
        self.prompt = get_filter_parsing_prompt()
        self.parser = JsonOutputParser()
    
    async def parse_filter_query(self, query: str) -> FilterResponse:
        """Parse a natural language query into structured filters."""
        logger.info("Parsing filter query", query=query)
        
        try:
            # Create parsing prompt
            messages = self.prompt.format_messages(query=query)
            
            # Add JSON output instruction
            messages.append({
                "role": "system",
                "content": "Return only valid JSON array of filter objects. No additional text."
            })
            
            # Get LLM response
            response = await self.llm.ainvoke(messages)
            response_text = response.content
            
            # Parse JSON response
            try:
                # Try to extract JSON from response
                json_start = response_text.find('[')
                json_end = response_text.rfind(']') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_text = response_text[json_start:json_end]
                    filters_data = json.loads(json_text)
                else:
                    filters_data = json.loads(response_text)
                
                # Convert to DashboardFilter objects
                filters = [
                    DashboardFilter(
                        field=f.get('field'),
                        operator=f.get('operator'),
                        value=f.get('value')
                    )
                    for f in filters_data
                ]
                
                result = FilterResponse(
                    filters=filters,
                    raw_query=query,
                    confidence=0.95 if filters else 0.5
                )
                
                logger.info("Query parsed successfully", filter_count=len(filters))
                return result
                
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse JSON response", error=str(e))
                
                # Fallback: create simple filter based on keywords
                return self._create_fallback_filter(query)
                
        except Exception as e:
            logger.error("Query parsing failed", error=str(e))
            return self._create_fallback_filter(query)
    
    def _create_fallback_filter(self, query: str) -> FilterResponse:
        """Create a simple fallback filter when parsing fails."""
        query_lower = query.lower()
        filters = []
        
        # Simple keyword matching
        if "running" in query_lower:
            filters.append(DashboardFilter(
                field="status",
                operator="equals",
                value="Running"
            ))
        elif "pending" in query_lower:
            filters.append(DashboardFilter(
                field="status",
                operator="equals",
                value="Pending"
            ))
        elif "failed" in query_lower or "error" in query_lower:
            filters.append(DashboardFilter(
                field="status",
                operator="equals",
                value="Failed"
            ))
        
        return FilterResponse(
            filters=filters,
            raw_query=query,
            confidence=0.3  # Low confidence for fallback
        )


def get_query_parser() -> QueryParserService:
    """Get query parser service instance."""
    return QueryParserService()
