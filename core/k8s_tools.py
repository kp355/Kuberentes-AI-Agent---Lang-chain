"""LangChain Tools for Kubernetes Operations."""
from langchain_core.tools import tool
from kubernetes import client, config as k8s_config
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()


class KubernetesTools:
    """Collection of LangChain tools for Kubernetes operations."""
    
    def __init__(self, kubeconfig_path: Optional[str] = None):
        """Initialize Kubernetes client."""
        try:
            if kubeconfig_path:
                k8s_config.load_kube_config(config_file=kubeconfig_path)
            else:
                k8s_config.load_kube_config()
            
            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            logger.info("Kubernetes client initialized")
        except Exception as e:
            logger.error("Failed to initialize Kubernetes client", error=str(e))
            raise
    
    @tool
    def list_pods(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """List all pods in a namespace with their current status.
        
        Args:
            namespace: Kubernetes namespace (default: "default")
            
        Returns:
            List of pod information including name, status, restarts, and age
        """
        try:
            pods = self.core_v1.list_namespaced_pod(namespace=namespace)
            
            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "restarts": sum([cs.restart_count for cs in pod.status.container_statuses or []]),
                    "age": str(datetime.now() - pod.metadata.creation_timestamp.replace(tzinfo=None)),
                    "node": pod.spec.node_name,
                    "ip": pod.status.pod_ip,
                }
                pod_list.append(pod_info)
            
            logger.info(f"Listed {len(pod_list)} pods", namespace=namespace)
            return pod_list
            
        except Exception as e:
            logger.error("Error listing pods", error=str(e), namespace=namespace)
            return [{"error": str(e)}]
    
    @tool
    def get_pod_logs(self, pod_name: str, namespace: str = "default", tail_lines: int = 100) -> str:
        """Get recent logs from a specific pod.
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            tail_lines: Number of recent log lines to retrieve
            
        Returns:
            Pod logs as a string
        """
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines
            )
            logger.info("Retrieved pod logs", pod=pod_name, namespace=namespace)
            return logs
            
        except Exception as e:
            error_msg = f"Error getting logs for pod {pod_name}: {str(e)}"
            logger.error(error_msg, pod=pod_name, namespace=namespace)
            return error_msg
    
    @tool
    def get_pod_events(self, pod_name: str, namespace: str = "default") -> List[Dict[str, Any]]:
        """Get recent events for a specific pod to understand failures.
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            
        Returns:
            List of recent events related to the pod
        """
        try:
            events = self.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}"
            )
            
            event_list = []
            for event in events.items:
                event_info = {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "timestamp": str(event.last_timestamp or event.first_timestamp),
                }
                event_list.append(event_info)
            
            # Sort by timestamp, most recent first
            event_list.sort(key=lambda x: x["timestamp"], reverse=True)
            
            logger.info(f"Retrieved {len(event_list)} events", pod=pod_name, namespace=namespace)
            return event_list
            
        except Exception as e:
            logger.error("Error getting pod events", error=str(e), pod=pod_name)
            return [{"error": str(e)}]
    
    @tool
    def describe_pod(self, pod_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get detailed information about a specific pod including status, conditions, and containers.
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            
        Returns:
            Detailed pod information
        """
        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "conditions": [
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason,
                        "message": c.message
                    } for c in (pod.status.conditions or [])
                ],
                "containers": [
                    {
                        "name": c.name,
                        "image": c.image,
                        "state": self._get_container_state(cs),
                        "ready": cs.ready,
                        "restarts": cs.restart_count,
                    } for c, cs in zip(pod.spec.containers, pod.status.container_statuses or [])
                ],
                "node": pod.spec.node_name,
                "ip": pod.status.pod_ip,
                "created": str(pod.metadata.creation_timestamp),
            }
            
            logger.info("Described pod", pod=pod_name, namespace=namespace)
            return pod_info
            
        except Exception as e:
            logger.error("Error describing pod", error=str(e), pod=pod_name)
            return {"error": str(e)}
    
    @tool
    def get_namespace_resources(self, namespace: str = "default") -> Dict[str, Any]:
        """Get resource usage summary for a namespace including CPU and memory.
        
        Args:
            namespace: Kubernetes namespace
            
        Returns:
            Resource usage information
        """
        try:
            pods = self.core_v1.list_namespaced_pod(namespace=namespace)
            
            total_cpu_requests = 0
            total_memory_requests = 0
            total_cpu_limits = 0
            total_memory_limits = 0
            
            for pod in pods.items:
                for container in pod.spec.containers:
                    if container.resources.requests:
                        cpu = container.resources.requests.get('cpu', '0')
                        memory = container.resources.requests.get('memory', '0')
                        total_cpu_requests += self._parse_cpu(cpu)
                        total_memory_requests += self._parse_memory(memory)
                    
                    if container.resources.limits:
                        cpu = container.resources.limits.get('cpu', '0')
                        memory = container.resources.limits.get('memory', '0')
                        total_cpu_limits += self._parse_cpu(cpu)
                        total_memory_limits += self._parse_memory(memory)
            
            resource_info = {
                "namespace": namespace,
                "pod_count": len(pods.items),
                "cpu_requests": f"{total_cpu_requests}m",
                "memory_requests": f"{total_memory_requests}Mi",
                "cpu_limits": f"{total_cpu_limits}m",
                "memory_limits": f"{total_memory_limits}Mi",
            }
            
            logger.info("Retrieved namespace resources", namespace=namespace)
            return resource_info
            
        except Exception as e:
            logger.error("Error getting namespace resources", error=str(e))
            return {"error": str(e)}
    
    def _get_container_state(self, container_status) -> str:
        """Extract container state from status."""
        if container_status.state.running:
            return "running"
        elif container_status.state.waiting:
            return f"waiting: {container_status.state.waiting.reason}"
        elif container_status.state.terminated:
            return f"terminated: {container_status.state.terminated.reason}"
        return "unknown"
    
    def _parse_cpu(self, cpu_str: str) -> int:
        """Parse CPU string to millicores."""
        if not cpu_str or cpu_str == '0':
            return 0
        if 'm' in cpu_str:
            return int(cpu_str.replace('m', ''))
        return int(float(cpu_str) * 1000)
    
    def _parse_memory(self, memory_str: str) -> int:
        """Parse memory string to MiB."""
        if not memory_str or memory_str == '0':
            return 0
        
        units = {'Ki': 1/1024, 'Mi': 1, 'Gi': 1024, 'Ti': 1024*1024}
        for unit, multiplier in units.items():
            if unit in memory_str:
                return int(float(memory_str.replace(unit, '')) * multiplier)
        return int(memory_str)


def get_k8s_tools(kubeconfig_path: Optional[str] = None) -> List:
    """Get list of Kubernetes tools for LangChain agent."""
    k8s = KubernetesTools(kubeconfig_path)
    
    return [
        k8s.list_pods,
        k8s.get_pod_logs,
        k8s.get_pod_events,
        k8s.describe_pod,
        k8s.get_namespace_resources,
    ]
