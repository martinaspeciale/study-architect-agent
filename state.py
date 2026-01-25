from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

class Resource(BaseModel):
    title: str = Field(description="Title of the academic resource")
    url: str = Field(description="URL of the resource")
    summary: str = Field(default="No summary available.") 
    type: str = Field(description="Type of resource (Video, Article, Paper)")

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    topic: str
    syllabus: List[str]
    resources: List[Resource]
    feedback: Optional[str]
    is_approved: bool
    retry_count: int