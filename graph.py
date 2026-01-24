from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import planner_node, finder_node, judge_node

def router(state: AgentState):
    if state["is_approved"] or state["retry_count"] > 3:
        return "end"
    return "retry"

workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("finder", finder_node)
workflow.add_node("judge", judge_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "finder")
workflow.add_edge("finder", "judge")

workflow.add_conditional_edges(
    "judge",
    router,
    {"end": END, "retry": "planner"}
)

app = workflow.compile()

if __name__ == "__main__":
    initial = {"topic": "Machine Learning Ethics", "retry_count": 0}
    for event in app.stream(initial):
        pass