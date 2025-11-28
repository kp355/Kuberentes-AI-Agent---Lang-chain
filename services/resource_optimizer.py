"""Resource optimization service using LangChain."""
from models.ai import get_llm
from models.prompt import get_resource_optimization_prompt
from models.model import ResourceRecommendation, RecommendationResponse
from core.k8s_tools import KubernetesTools
import structlog
from typing import List

logger = structlog.get_logger()


class ResourceOptimizerService:
    """Service for analyzing and optimizing Kubernetes resource usage."""
    
    def __init__(self, kubeconfig_path: str = None):
        self.llm = get_llm()
        self.k8s = KubernetesTools(kubeconfig_path)
        self.prompt = get_resource_optimization_prompt()
    
    async def get_recommendations(self, namespace: str = "default") -> RecommendationResponse:
        """Get resource optimization recommendations for a namespace."""
        logger.info("Generating recommendations", namespace=namespace)
        
        try:
            # Gather resource usage data
            resource_data = self.k8s.get_namespace_resources(namespace)
            pods = self.k8s.list_pods(namespace)
            
            # Format data for LLM
            resource_text = f"""
Namespace: {namespace}
Total Pods: {resource_data.get('pod_count', 0)}

Resource Requests:
- CPU: {resource_data.get('cpu_requests', '0')}
- Memory: {resource_data.get('memory_requests', '0')}

Resource Limits:
- CPU: {resource_data.get('cpu_limits', '0')}
- Memory: {resource_data.get('memory_limits', '0')}

Pod Details:
"""
            for pod in pods[:10]:  # Analyze top 10 pods
                resource_text += f"\n- {pod['name']}: {pod['status']} (restarts: {pod['restarts']})"
            
            # Create optimization prompt
            messages = self.prompt.format_messages(
                namespace=namespace,
                resource_data=resource_text
            )
            
            # Get AI recommendations
            response = await self.llm.ainvoke(messages)
            recommendations_text = response.content
            
            # Parse recommendations
            recommendations = self._parse_recommendations(recommendations_text, namespace)
            
            # Generate summary
            summary = self._generate_summary(recommendations)
            
            result = RecommendationResponse(
                recommendations=recommendations,
                summary=summary,
                total_potential_savings="$50-200/month (estimated)"
            )
            
            logger.info("Recommendations generated", count=len(recommendations))
            return result
            
        except Exception as e:
            logger.error("Recommendation generation failed", error=str(e))
            return RecommendationResponse(
                recommendations=[],
                summary=f"Failed to generate recommendations: {str(e)}",
                total_potential_savings=None
            )
    
    def _parse_recommendations(self, text: str, namespace: str) -> List[ResourceRecommendation]:
        """Parse recommendations from LLM response."""
        recommendations = []
        
        # Split into sections
        sections = text.split('\n\n')
        
        for section in sections:
            # Look for recommendation patterns
            if any(keyword in section.lower() for keyword in ['recommend', 'reduce', 'increase', 'optimize']):
                # Extract resource name
                lines = section.split('\n')
                resource_name = "unknown"
                
                for line in lines:
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) > 1:
                            resource_name = parts[0].strip()
                            break
                
                # Create recommendation
                rec = ResourceRecommendation(
                    resource_type="pod",
                    resource_name=resource_name,
                    namespace=namespace,
                    current_usage={"cpu": "unknown", "memory": "unknown"},
                    recommended_limits={"cpu": "TBD", "memory": "TBD"},
                    potential_savings="$10-50/month",
                    priority="medium",
                    reasoning=section[:200]  # First 200 chars
                )
                recommendations.append(rec)
        
        return recommendations[:5]  # Top 5 recommendations
    
    def _generate_summary(self, recommendations: List[ResourceRecommendation]) -> str:
        """Generate summary of recommendations."""
        if not recommendations:
            return "No optimization opportunities found. Resources are well-configured."
        
        high_priority = len([r for r in recommendations if r.priority == "high"])
        medium_priority = len([r for r in recommendations if r.priority == "medium"])
        
        return f"""Found {len(recommendations)} optimization opportunities:
- {high_priority} high priority
- {medium_priority} medium priority

Key actions: Review resource limits and requests for over-provisioned pods."""


def get_resource_optimizer(kubeconfig_path: str = None) -> ResourceOptimizerService:
    """Get resource optimizer service instance."""
    return ResourceOptimizerService(kubeconfig_path)
