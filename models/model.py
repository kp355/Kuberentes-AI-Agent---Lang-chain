"""Pydantic models for API requests and responses."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class QueryRequest(BaseModel):
    """User query request."""
    prompt: str = Field(..., description="Natural language query about Kubernetes")
    cluster_id: Optional[str] = Field(None, description="Kubernetes cluster identifier")
    namespace: Optional[str] = Field("default", description="Kubernetes namespace")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")


class QueryResponse(BaseModel):
    """AI assistant response."""
    response: str = Field(..., description="Natural language response")
    analysis: Optional[Dict[str, Any]] = Field(None, description="Detailed analysis")
    suggestions: Optional[List[str]] = Field(None, description="Remediation suggestions")
    confidence: Optional[float] = Field(None, description="Confidence score")
    execution_time: Optional[float] = Field(None, description="Query execution time in seconds")


class FilterOperator(str, Enum):
    """Filter operators."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


class DashboardFilter(BaseModel):
    """Dashboard filter model."""
    field: str = Field(..., description="Field to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: Any = Field(..., description="Filter value")


class FilterResponse(BaseModel):
    """Filter query response."""
    filters: List[DashboardFilter] = Field(..., description="Parsed filters")
    raw_query: str = Field(..., description="Original query")
    confidence: float = Field(..., description="Parsing confidence")


class ResourceRecommendation(BaseModel):
    """Resource optimization recommendation."""
    resource_type: str = Field(..., description="Type of resource (pod, deployment, etc.)")
    resource_name: str = Field(..., description="Name of the resource")
    namespace: str = Field(..., description="Kubernetes namespace")
    current_usage: Dict[str, Any] = Field(..., description="Current resource usage")
    recommended_limits: Dict[str, Any] = Field(..., description="Recommended resource limits")
    potential_savings: Optional[str] = Field(None, description="Estimated cost savings")
    priority: str = Field(..., description="Priority level (high, medium, low)")
    reasoning: str = Field(..., description="AI reasoning for recommendation")


class RecommendationResponse(BaseModel):
    """Recommendation response."""
    recommendations: List[ResourceRecommendation] = Field(..., description="List of recommendations")
    summary: str = Field(..., description="Summary of recommendations")
    total_potential_savings: Optional[str] = Field(None, description="Total estimated savings")


class PodStatus(BaseModel):
    """Pod status information."""
    name: str
    namespace: str
    status: str
    restarts: int
    age: str
    node: Optional[str] = None


class PodDiagnostics(BaseModel):
    """Pod diagnostics result."""
    pod_name: str
    namespace: str
    status: str
    issues: List[str]
    root_cause: Optional[str] = None
    remediation_steps: List[str]
    logs_summary: Optional[str] = None
    events_summary: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "2.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    components: Dict[str, str] = Field(default_factory=dict)
