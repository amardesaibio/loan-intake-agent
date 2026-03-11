from fastapi import APIRouter
router = APIRouter()

@router.get("/status/{session_id}")
async def get_application_status(session_id: str):
    return {"session_id": session_id, "status": "in_progress"}
