"""Kubernetes tools for LangChain/LangGraph integration."""
from typing import List, Optional, Dict, Any
from langchain_core.tools import tool
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException
import structlog
from datetime import datetime

logger = structlog.get_logger()

# Global Kubernetes clients
_k8s_core_v1: Optional[client.CoreV1Api] = None
_k8s_apps_v1: Optional[client.AppsV1Api] = None


def init_k8s_client(kubeconfig_path: str = None):
    """Initialize Kubernetes client."""
    global _k8s_core_v1, _k8s_apps_v1
    
    try:
        if kubeconfig_path:
            k8s_config.load_kube_config(config_file=kubeconfig_path)
            logger.info("Loaded kubeconfig from path", path=kubeconfig_path)
        else:
            try:
                k8s_config.load_incluster_config()
                logger.info("Loaded in-cluster config")
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()
                logger.info("Loaded default kubeconfig")
        
        _k8s_core_v1 = client.CoreV1Api()
        _k8s_apps_v1 = client.AppsV1Api()
        logger.info("Kubernetes client initialized")
        
    except Exception as e:
        logger.error("Failed to initialize Kubernetes client", error=str(e))
        raise


def get_core_v1() -> client.CoreV1Api:
    """Get CoreV1Api client."""
    global _k8s_core_v1
    if _k8s_core_v1 is None:
        init_k8s_client()
    return _k8s_core_v1


def get_apps_v1() -> client.AppsV1Api:
    """Get AppsV1Api client."""
    global _k8s_apps_v1
    if _k8s_apps_v1 is None:
        init_k8s_client()
    return _k8s_apps_v1


@tool
def list_pods(namespace: str = "default") -> str:
    """List all pods in a namespace with their status.
    
    Args:
        namespace: The Kubernetes namespace to list pods from. Defaults to 'default'.
    
    Returns:
        A formatted string with pod names, status, and restart counts.
    """
    try:
        v1 = get_core_v1()
        pods = v1.list_namespaced_pod(namespace=namespace)
        
        if not pods.items:
            return f"No pods found in namespace '{namespace}'"
        
        result = f"Pods in namespace '{namespace}':\n\n"
        for pod in pods.items:
            status = pod.status.phase
            restarts = 0
            ready = "0/0"
            
            if pod.status.container_statuses:
                restarts = sum(cs.restart_count for cs in pod.status.container_statuses)
                ready_count = sum(1 for cs in pod.status.container_statuses if cs.ready)
                total_count = len(pod.status.container_statuses)
                ready = f"{ready_count}/{total_count}"
            
            result += f"- {pod.metadata.name}\n"
            result += f"  Status: {status} | Ready: {ready} | Restarts: {restarts}\n"
            
            # Add container status details if not running
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    if cs.state.waiting:
                        result += f"  Container '{cs.name}' waiting: {cs.state.waiting.reason}\n"
                    elif cs.state.terminated:
                        result += f"  Container '{cs.name}' terminated: {cs.state.terminated.reason}\n"
        
        return result
        
    except ApiException as e:
        return f"Error listing pods: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_pod_logs(pod_name: str, namespace: str = "default", tail_lines: int = 100) -> str:
    """Get logs from a specific pod.
    
    Args:
        pod_name: Name of the pod to get logs from.
        namespace: The Kubernetes namespace. Defaults to 'default'.
        tail_lines: Number of log lines to retrieve. Defaults to 100.
    
    Returns:
        The pod logs as a string.
    """
    try:
        v1 = get_core_v1()
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=tail_lines
        )
        
        if not logs:
            return f"No logs available for pod '{pod_name}'"
        
        return f"Logs for pod '{pod_name}' (last {tail_lines} lines):\n\n{logs}"
        
    except ApiException as e:
        return f"Error getting logs: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_pod_events(pod_name: str, namespace: str = "default") -> str:
    """Get events related to a specific pod.
    
    Args:
        pod_name: Name of the pod to get events for.
        namespace: The Kubernetes namespace. Defaults to 'default'.
    
    Returns:
        A formatted string with events related to the pod.
    """
    try:
        v1 = get_core_v1()
        field_selector = f"involvedObject.name={pod_name}"
        events = v1.list_namespaced_event(
            namespace=namespace,
            field_selector=field_selector
        )
        
        if not events.items:
            return f"No events found for pod '{pod_name}'"
        
        result = f"Events for pod '{pod_name}':\n\n"
        for event in sorted(events.items, key=lambda x: x.last_timestamp or x.event_time or datetime.min, reverse=True):
            timestamp = event.last_timestamp or event.event_time
            result += f"- [{event.type}] {event.reason}: {event.message}\n"
            result += f"  Time: {timestamp}\n\n"
        
        return result
        
    except ApiException as e:
        return f"Error getting events: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Get detailed description of a pod including containers, volumes, and conditions.
    
    Args:
        pod_name: Name of the pod to describe.
        namespace: The Kubernetes namespace. Defaults to 'default'.
    
    Returns:
        A detailed description of the pod.
    """
    try:
        v1 = get_core_v1()
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        
        result = f"Pod: {pod.metadata.name}\n"
        result += f"Namespace: {pod.metadata.namespace}\n"
        result += f"Node: {pod.spec.node_name}\n"
        result += f"Status: {pod.status.phase}\n"
        result += f"IP: {pod.status.pod_ip}\n\n"
        
        # Conditions
        result += "Conditions:\n"
        if pod.status.conditions:
            for cond in pod.status.conditions:
                result += f"  - {cond.type}: {cond.status}"
                if cond.reason:
                    result += f" ({cond.reason})"
                result += "\n"
        
        # Containers
        result += "\nContainers:\n"
        for container in pod.spec.containers:
            result += f"  - {container.name}\n"
            result += f"    Image: {container.image}\n"
            
            # Resources
            if container.resources:
                if container.resources.requests:
                    result += f"    Requests: {container.resources.requests}\n"
                if container.resources.limits:
                    result += f"    Limits: {container.resources.limits}\n"
        
        # Container statuses
        if pod.status.container_statuses:
            result += "\nContainer Statuses:\n"
            for cs in pod.status.container_statuses:
                result += f"  - {cs.name}: Ready={cs.ready}, Restarts={cs.restart_count}\n"
                if cs.state.waiting:
                    result += f"    State: Waiting - {cs.state.waiting.reason}\n"
                elif cs.state.running:
                    result += f"    State: Running since {cs.state.running.started_at}\n"
                elif cs.state.terminated:
                    result += f"    State: Terminated - {cs.state.terminated.reason}\n"
        
        return result
        
    except ApiException as e:
        return f"Error describing pod: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def list_deployments(namespace: str = "default") -> str:
    """List all deployments in a namespace.
    
    Args:
        namespace: The Kubernetes namespace. Defaults to 'default'.
    
    Returns:
        A formatted string with deployment information.
    """
    try:
        apps_v1 = get_apps_v1()
        deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
        
        if not deployments.items:
            return f"No deployments found in namespace '{namespace}'"
        
        result = f"Deployments in namespace '{namespace}':\n\n"
        for dep in deployments.items:
            ready = dep.status.ready_replicas or 0
            desired = dep.spec.replicas or 0
            available = dep.status.available_replicas or 0
            
            result += f"- {dep.metadata.name}\n"
            result += f"  Ready: {ready}/{desired} | Available: {available}\n"
            
            # Check conditions
            if dep.status.conditions:
                for cond in dep.status.conditions:
                    if cond.type == "Available" and cond.status != "True":
                        result += f"  Warning: Not Available - {cond.message}\n"
                    elif cond.type == "Progressing" and cond.status != "True":
                        result += f"  Warning: Not Progressing - {cond.message}\n"
        
        return result
        
    except ApiException as e:
        return f"Error listing deployments: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_nodes() -> str:
    """Get status of all nodes in the cluster.
    
    Returns:
        A formatted string with node information and conditions.
    """
    try:
        v1 = get_core_v1()
        nodes = v1.list_node()
        
        if not nodes.items:
            return "No nodes found in cluster"
        
        result = "Cluster Nodes:\n\n"
        for node in nodes.items:
            result += f"- {node.metadata.name}\n"
            
            # Node info
            if node.status.node_info:
                info = node.status.node_info
                result += f"  OS: {info.os_image}\n"
                result += f"  Kubelet: {info.kubelet_version}\n"
            
            # Conditions
            if node.status.conditions:
                for cond in node.status.conditions:
                    if cond.type == "Ready":
                        status = "Ready" if cond.status == "True" else "Not Ready"
                        result += f"  Status: {status}\n"
                    elif cond.status == "True" and cond.type != "Ready":
                        result += f"  Warning {cond.type}: {cond.message}\n"
            
            # Capacity
            if node.status.capacity:
                result += f"  CPU: {node.status.capacity.get('cpu', 'N/A')}\n"
                result += f"  Memory: {node.status.capacity.get('memory', 'N/A')}\n"
            
            result += "\n"
        
        return result
        
    except ApiException as e:
        return f"Error getting nodes: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def list_namespaces() -> str:
    """List all namespaces in the cluster.
    
    Returns:
        A formatted string with namespace names and status.
    """
    try:
        v1 = get_core_v1()
        namespaces = v1.list_namespace()
        
        if not namespaces.items:
            return "No namespaces found"
        
        result = "Namespaces:\n\n"
        for ns in namespaces.items:
            status = ns.status.phase
            result += f"- {ns.metadata.name} ({status})\n"
        
        return result
        
    except ApiException as e:
        return f"Error listing namespaces: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


def get_k8s_tools(kubeconfig_path: str = None) -> List:
    """Get all Kubernetes tools for the agent."""
    # Initialize the client
    init_k8s_client(kubeconfig_path)
    
    return [
        list_pods,
        get_pod_logs,
        get_pod_events,
        describe_pod,
        list_deployments,
        get_nodes,
        list_namespaces,
    ]


class KubernetesTools:
    """Kubernetes tools wrapper class for direct API access (non-LangChain usage)."""
    
    def __init__(self, kubeconfig_path: str = None):
        init_k8s_client(kubeconfig_path)
    
    def list_pods(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """List pods as structured data."""
        try:
            v1 = get_core_v1()
            pods = v1.list_namespaced_pod(namespace=namespace)
            
            result = []
            for pod in pods.items:
                restarts = 0
                if pod.status.container_statuses:
                    restarts = sum(cs.restart_count for cs in pod.status.container_statuses)
                
                result.append({
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "restarts": restarts,
                    "namespace": namespace
                })
            return result
        except Exception as e:
            logger.error("Error listing pods", error=str(e))
            return []
    
    def describe_pod(self, pod_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get pod description as structured data."""
        try:
            v1 = get_core_v1()
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            containers = []
            for container in pod.spec.containers:
                containers.append({
                    "name": container.name,
                    "image": container.image
                })
            
            conditions = []
            if pod.status.conditions:
                for cond in pod.status.conditions:
                    conditions.append({
                        "type": cond.type,
                        "status": cond.status,
                        "reason": cond.reason
                    })
            
            return {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "node": pod.spec.node_name,
                "ip": pod.status.pod_ip,
                "containers": containers,
                "conditions": conditions
            }
        except Exception as e:
            logger.error("Error describing pod", error=str(e))
            return {"status": "error", "error": str(e)}
    
    def get_pod_logs(self, pod_name: str, namespace: str = "default", tail_lines: int = 100) -> str:
        """Get pod logs."""
        try:
            v1 = get_core_v1()
            logs = v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=tail_lines
            )
            return logs if logs else ""
        except Exception as e:
            logger.error("Error getting pod logs", error=str(e))
            return ""
    
    def get_pod_events(self, pod_name: str, namespace: str = "default") -> List[Dict[str, Any]]:
        """Get pod events as structured data."""
        try:
            v1 = get_core_v1()
            field_selector = f"involvedObject.name={pod_name}"
            events = v1.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector
            )
            
            result = []
            for event in events.items:
                result.append({
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "timestamp": str(event.last_timestamp or event.event_time)
                })
            return result
        except Exception as e:
            logger.error("Error getting pod events", error=str(e))
            return []
    
    def get_namespace_resources(self, namespace: str = "default") -> Dict[str, Any]:
        """Get aggregate resource usage for a namespace."""
        try:
            v1 = get_core_v1()
            pods = v1.list_namespaced_pod(namespace=namespace)
            
            cpu_requests = 0
            memory_requests = 0
            cpu_limits = 0
            memory_limits = 0
            
            for pod in pods.items:
                for container in pod.spec.containers:
                    if container.resources:
                        if container.resources.requests:
                            cpu_req = container.resources.requests.get('cpu', '0')
                            mem_req = container.resources.requests.get('memory', '0')
                            cpu_requests += self._parse_cpu(cpu_req)
                            memory_requests += self._parse_memory(mem_req)
                        if container.resources.limits:
                            cpu_lim = container.resources.limits.get('cpu', '0')
                            mem_lim = container.resources.limits.get('memory', '0')
                            cpu_limits += self._parse_cpu(cpu_lim)
                            memory_limits += self._parse_memory(mem_lim)
            
            return {
                "pod_count": len(pods.items),
                "cpu_requests": f"{cpu_requests}m",
                "memory_requests": f"{memory_requests}Mi",
                "cpu_limits": f"{cpu_limits}m",
                "memory_limits": f"{memory_limits}Mi"
            }
        except Exception as e:
            logger.error("Error getting namespace resources", error=str(e))
            return {"pod_count": 0, "error": str(e)}
    
    def _parse_cpu(self, cpu_str: str) -> int:
        """Parse CPU string to millicores."""
        if not cpu_str or cpu_str == '0':
            return 0
        cpu_str = str(cpu_str)
        if cpu_str.endswith('m'):
            return int(cpu_str[:-1])
        return int(float(cpu_str) * 1000)
    
    def _parse_memory(self, mem_str: str) -> int:
        """Parse memory string to Mi."""
        if not mem_str or mem_str == '0':
            return 0
        mem_str = str(mem_str)
        if mem_str.endswith('Mi'):
            return int(mem_str[:-2])
        if mem_str.endswith('Gi'):
            return int(mem_str[:-2]) * 1024
        if mem_str.endswith('Ki'):
            return int(mem_str[:-2]) // 1024
        return int(mem_str) // (1024 * 1024)
