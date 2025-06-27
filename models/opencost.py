# import requests
# from fastapi import HTTPException
# from models.DBsupabase import supabase

# def get_opencost_url_for_cluster(cluster_name: str) -> str:
#     response = supabase.table("clusters").select("opencost_url").eq("name", cluster_name).single().execute()
#     if response.data and "opencost_url" in response.data:
#         return response.data["opencost_url"]
#     raise HTTPException(status_code=404, detail=f"No OpenCost URL found for cluster '{cluster_name}'")

# def get_allocation(cluster_name: str, window="7d", node_name=None):
#     baseUrl = get_opencost_url_for_cluster(cluster_name)
#     URL = baseUrl + '/model/allocation/compute'

#     params = {
#         "window": window,
#         "aggregate": "namespace",
#         "includeIdle": "true",
#         "accumulate": "true"
#     }

#     response = requests.get(URL, params=params, timeout=30)
#     response.raise_for_status()
#     raw_data = response.json()["data"][0]
#     results = []

#     for key, entry in raw_data.items():
#         actual_node = entry["properties"].get("node")

#         if node_name and actual_node != node_name:
#             continue

#         results.append({
#             "name": entry.get("name"),
#             "node": actual_node,
#             "namespace": entry["properties"].get("namespace"),
#             "pod": entry["properties"].get("pod"),
#             "container": entry["properties"].get("container"),
#             "instanceType": entry["properties"].get("labels", {}).get("beta_kubernetes_io_instance_type", "unknown"),
#             "cpuCores": entry.get("cpuCores", 0),
#             "cpuCoreUsageAverage": entry.get("cpuCoreUsageAverage", 0),
#             "ramBytes": entry.get("ramBytes", 0),
#             "networkReceiveBytes": entry.get("networkReceiveBytes", 0),
#             "networkTransferBytes": entry.get("networkTransferBytes", 0),
#             "cpuCost": entry.get("cpuCost", 0),
#             "pvCost": entry.get("pvCost", 0),
#             "ramCost": entry.get("ramCost", 0),
#             "totalCost": entry.get("totalCost", 0),
#             "window": window
#         })

#     return results
