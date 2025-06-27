def build_ai_prompt(node_data):
    return f"""You are a Kubernetes cost-optimization expert.

Assume these workloads run on AWS and you can choose from the current On-Demand
EC2 lines (t3, t4g, m7g, c7a, r7g, etc.).

Below are the key weekly averages for ONE node:

• Current instance type: {node_data.get("instanceType", "unknown")}
• CPU-cores average: {node_data["cpuCoreUsageAverage"]:.4f} cores  
• RAM usage: {node_data["ramBytes"]/1024/1024:.2f} MiB  
• Total weekly CPU cost: ${node_data["cpuCost"]:.2f}  
• Network in: {node_data["networkReceiveBytes"]/1024/1024:.2f} MiB  
• Network out: {node_data["networkTransferBytes"]/1024/1024:.2f} MiB

Task:  
Based on this usage, recommend 1 **better-fit** EC2 instance types than the current one.
List instance type in this format (1 line each):

<instance_type> - <one-line reason>

Start with the most preferred option.
"""
