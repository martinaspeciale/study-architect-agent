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
    print("\n" + "="*40)
    print("MULTI-AGENT STUDY ARCHITECT")
    print("="*40)
    
    user_topic = input("\nEnter the topic you want to study: ").strip()
    
    # Fallback (if user_topic not provided)
    if not user_topic:
        user_topic = "Machine Learning Ethics"
        print(f"No input provided. Using default: {user_topic}")
    
    initial_state = {
        "topic": user_topic, 
        "retry_count": 0,
        "feedback": None,
        "is_approved": False,
        "syllabus": [],   
        "resources": []
    }
    
    print(f"\nStarting workflow for: '{user_topic}'...\n")
    
    # Start the graph
    for event in app.stream(initial_state):
        # expose state transitions and inter-agent message passing in CLI
        for node_name, output_data in event.items():
            print(f"\n📨 MESSAGE PASSING (From: {node_name.upper()})")
            print(f"   Payload: {output_data}")
            print("-" * 40)
        
    print("\n" + "="*40)
    print("PROCESS COMPLETED")
    print("="*40)