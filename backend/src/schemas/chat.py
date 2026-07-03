from pydantic import BaseModel, Field
from typing import List

class SuggestionList(BaseModel):
    questions: List[str] = Field(
        description="A list of 3 specific follow-up questions based on the chat context.",
        min_items=3,
        max_items=3
    )
