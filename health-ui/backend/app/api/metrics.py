from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics/test")
def test_metric():
    return {
        "metric": "up",
        "value": 1,
        "source": "mock"
    }
