"""Pod diagnostics service using LangChain."""
from models.ai import get_llm
from models.prompt import get_pod_diagnosis_prompt
from models.model import PodDiagnostics
from core.k8s_tools import KubernetesTools
import structlog

logger = structlog.get_logger()


class PodDiagnosticsService:
    """Service for diagnosing pod failures using LangChain."""
    
    def __init__(self, kubeconfig_path: str = None):
        self.llm = get_llm()
        self.k8s = KubernetesTools(kubeconfig_path)
        self.prompt = get_pod_diagnosis_prompt()
    
    async def diagnose_pod(self, pod_name: str, namespace: str = "default") -> PodDiagnostics:
        """Diagnose a pod failure and provide remediation steps."""
        logger.info("Diagnosing pod", pod=pod_name, namespace=namespace)
        
        try:
            # Gather pod information
            pod_info = self.k8s.describe_pod(pod_name, namespace)
            logs = self.k8s.get_pod_logs(pod_name, namespace, tail_lines=50)
            events = self.k8s.get_pod_events(pod_name, namespace)
            
            # Format context for LLM
            pod_status = f"""
Status: {pod_info.get('status', 'unknown')}
Conditions: {pod_info.get('conditions', [])}
Containers: {pod_info.get('containers', [])}
"""
            
            events_text = "\n".join([
                f"[{e.get('type')}] {e.get('reason')}: {e.get('message')}"
                for e in events[:10]  # Last 10 events
            ])
            
            # Create diagnosis prompt
            messages = self.prompt.format_messages(
                pod_name=pod_name,
                namespace=namespace,
                pod_status=pod_status,
                logs=logs[:2000] if logs else "No logs available",
                events=events_text if events_text else "No events found"
            )
            
            # Get AI diagnosis
            response = await self.llm.ainvoke(messages)
            diagnosis_text = response.content
            
            # Parse response into structured format
            issues = self._extract_issues(diagnosis_text)
            root_cause = self._extract_root_cause(diagnosis_text)
            remediation_steps = self._extract_remediation(diagnosis_text)
            
            result = PodDiagnostics(
                pod_name=pod_name,
                namespace=namespace,
                status=pod_info.get('status', 'unknown'),
                issues=issues,
                root_cause=root_cause,
                remediation_steps=remediation_steps,
                logs_summary=logs[:500] if logs else None,
                events_summary=events_text[:500] if events_text else None
            )
            
            logger.info("Pod diagnosis completed", pod=pod_name)
            return result
            
        except Exception as e:
            logger.error("Pod diagnosis failed", error=str(e), pod=pod_name)
            return PodDiagnostics(
                pod_name=pod_name,
                namespace=namespace,
                status="error",
                issues=[f"Diagnosis failed: {str(e)}"],
                root_cause=None,
                remediation_steps=["Check cluster connectivity and permissions"]
            )
    
    def _extract_issues(self, text: str) -> list:
        """Extract issues from diagnosis text."""
        # Simple extraction - look for bullet points or numbered lists
        lines = text.split('\n')
        issues = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or line[0:2].replace('.', '').isdigit():
                issue = line.lstrip('-•0123456789. ').strip()
                if issue and len(issue) > 10:
                    issues.append(issue)
        
        return issues[:5] if issues else ["No specific issues identified"]
    
    def _extract_root_cause(self, text: str) -> str:
        """Extract root cause from diagnosis text."""
        # Look for "root cause" section
        text_lower = text.lower()
        if "root cause" in text_lower:
            start = text_lower.index("root cause")
            end = text_lower.find("\n\n", start)
            if end == -1:
                end = len(text)
            return text[start:end].strip()
        
        # Fallback: return first paragraph
        paragraphs = text.split('\n\n')
        return paragraphs[0] if paragraphs else None
    
    def _extract_remediation(self, text: str) -> list:
        """Extract remediation steps from diagnosis text."""
        # Look for "remediation" or "steps" section
        text_lower = text.lower()
        start_markers = ["remediation", "steps to fix", "solution", "fix"]
        
        steps = []
        for marker in start_markers:
            if marker in text_lower:
                start = text_lower.index(marker)
                section = text[start:].split('\n\n')[0]
                
                for line in section.split('\n'):
                    line = line.strip()
                    if line.startswith('-') or line.startswith('•') or line[0:2].replace('.', '').isdigit():
                        step = line.lstrip('-•0123456789. ').strip()
                        if step and len(step) > 10:
                            steps.append(step)
                
                if steps:
                    break
        
        return steps[:5] if steps else ["Review pod logs and events for more details"]


def get_pod_diagnostics_service(kubeconfig_path: str = None) -> PodDiagnosticsService:
    """Get pod diagnostics service instance."""
    return PodDiagnosticsService(kubeconfig_path)
