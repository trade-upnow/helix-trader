from pydantic import BaseModel


class StrategyResponse(BaseModel):
    id: str
    default_params: dict
