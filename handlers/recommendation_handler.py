from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from models.opencost import get_allocation
from models.prompt import build_ai_prompt
from models.ai import get_ai_suggestion

router = APIRouter()

@router.get("/")
def get_recommendations(cluster_name: str, window: str = "7d", node_name: str = None):
    try:
        results = get_allocation(cluster_name, window=window, node_name=node_name)
        recommendations = []

        for node_data in results:
            prompt = build_ai_prompt(node_data)
            suggestion = get_ai_suggestion(prompt)

            recommendations.append({
                "node_name": node_data["name"],
                "metrics": {
                    "cpu_cores_usage_average": node_data["cpuCoreUsageAverage"],
                    "cpu_cost": node_data["cpuCost"],
                    "ram_bytes": node_data["ramBytes"],
                    "instance_type": node_data["instanceType"],
                    "network_receive_bytes": node_data["networkReceiveBytes"],
                    "network_transfer_bytes": node_data["networkTransferBytes"]
                },
                "suggestion": suggestion
            })

        return JSONResponse(recommendations)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
