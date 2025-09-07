# app/main.py
from typing import Optional, Any, Dict
from fastapi import FastAPI
from pydantic import BaseModel, field_validator, StrictStr

class CalcRequest(BaseModel):
    task: StrictStr
    a: Optional[float] = None
    b: Optional[float] = None
    var: StrictStr = "x"   # <-- must be string; was likely float in your code

    @field_validator("a", "b", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        # Convert "" to None so float parsing doesn't explode
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v



{
  "task": "differentiate x^3 + 2*x",
  "var": "x"
}
