from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse
from models.prompt import build_ai_prompt
from models.ai import get_ai_suggestion
from typing import Dict, Any

router = APIRouter()


@router.post("/")
def get_recommendations(
    req: Dict[str, Any] = Body(...)
):
    try:
        # print("allocation", req)
        prompt = build_ai_prompt(req)  # allocation is a plain dict now
        suggestion = get_ai_suggestion(prompt)
        print("suggestion", suggestion)
        return {
            "metrics": req,
            "suggestion": suggestion,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))