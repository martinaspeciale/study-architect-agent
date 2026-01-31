from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

class Resource(BaseModel):
    title: str = Field(description="Title of the academic resource")
    url: str = Field(description="URL of the resource")
    summary: str = Field(default="No summary available.") 
    type: str = Field(description="Type of resource")

# --- IL FIX E' QUI SOTTO ---
class PlanSection(BaseModel):
    section_title: str = Field(description="Title of this study module")
    # Nota: default="..." rende il campo opzionale per Pydantic
    description: str = Field(default="Dettagli non disponibili.", description="Brief summary")
    queries: List[str] = Field(description="Search queries")

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    topic: str
    syllabus: List[str]
    resources: List[Resource]
    local_resources: List[Resource] 
    study_plan: List[PlanSection] 
    feedback: Optional[str]
    is_approved: bool
    retry_count: int
    search_type: str
    # Campo necessario per i log nella UI
    current_node_logs: Optional[str]