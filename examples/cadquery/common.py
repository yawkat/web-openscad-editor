"""Parameters shared by several models. Models share settings by importing them."""

from pydantic import BaseModel, Field


class PrintSettings(BaseModel):
    wall: float = Field(2.0, ge=1, le=5, multiple_of=0.2, description="Wall thickness in mm")
