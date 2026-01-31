from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# [Theory] The Artifact (Slide 14): Strict Pydantic models for handoffs
class Resource(BaseModel):
    title: str = Field(description="Title of the academic resource")
    url: str = Field(description="URL of the resource")
    summary: str = Field(default="No summary available.") 
    type: str = Field(description="Type of resource (Video, Article, Paper)")

# --- NEW: Hierarchical Structure ---
class PlanSection(BaseModel):
    section_title: str = Field(description="Title of this study module")
    description: str = Field(description="What the student should learn here")
    queries: List[str] = Field(description="Search queries to fill this section")

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    topic: str
    syllabus: List[str]
    resources: List[Resource]
    local_resources: List[Resource] 
    
    # [Theory] Hierarchical Planning (Slide 6)
    # Replaces flat 'web_syllabus' with structured 'study_plan'
    study_plan: List[PlanSection] 
    web_syllabus: List[str] # Kept for backward compatibility if needed
    
    feedback: Optional[str]
    is_approved: bool
    retry_count: int
    search_type: str