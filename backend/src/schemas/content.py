from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class PodcastTurn(BaseModel):
    speaker: Literal["Host (Jane)", "Expert (Tom)"]
    text: str

class PodcastScript(BaseModel):
    title: str
    scratchpad: str = Field(..., description="Thinking process for the script structure")
    dialogue: List[PodcastTurn]
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None

class QuizOption(BaseModel):
    label: str  
    text: str

class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_answer: str = Field(..., description="The label of the correct option (e.g., 'A')")
    explanation: str

class Quiz(BaseModel):
    title: str
    questions: List[QuizQuestion]

class Flashcard(BaseModel):
    front: str = Field(..., description="The question or concept on the front of the card")
    back: str = Field(..., description="The answer or definition on the back of the card")

class FlashcardDeck(BaseModel):
    title: str
    cards: List[Flashcard]

# --- Fix Recursive Schema ---
class MindMapNode(BaseModel):
    label: str = Field(..., description="The text label for this node")
    # Recursive field must be Optional or have default factory
    children: List["MindMapNode"] = Field(default_factory=list, description="Child nodes")

# Required for Pydantic to resolve the recursive type "MindMapNode"
MindMapNode.model_rebuild()

class MindMap(BaseModel):
    root: MindMapNode = Field(..., description="The central topic node")
    # Removed mermaid_syntax as we will generate structure first, or we can generate it from the tree if needed.
    # But for now let's stick to the tree structure which is cleaner for LLM to generate.
    # If the frontend needs mermaid, we can convert it there or in the generator.
    # Let's keep it simple: just the tree.
    mermaid_syntax: Optional[str] = Field(default="", description="Optional: Mermaid syntax representation")
