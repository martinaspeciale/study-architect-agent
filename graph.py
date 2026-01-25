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
    print("\n" + "="*100)
    print("MULTI-AGENT STUDY ARCHITECT")
    print("="*100)
    
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
            print(f"\n MESSAGE PASSING (From: {node_name.upper()})")
            print("-" * 100)

            # 1. PLANNER (modules' list)
            if "syllabus" in output_data and output_data["syllabus"]:
                print("    Proposed Syllabus:")
                for i, module in enumerate(output_data["syllabus"], 1):
                    print(f"      {i}. {module}")
            
            # 2. FINDER (Resource objects' list)
            elif "resources" in output_data and output_data["resources"]:
                print(f"    Resources Found ({len(output_data['resources'])}):")
                for res in output_data["resources"]:
                    print(f"      • {res.title}")
                    print(f"        - {res.url}")
            
            # 3. JUDGE (boolean + feedback)
            elif "is_approved" in output_data:
                status = " APPROVED" if output_data["is_approved"] else " REJECTED"
                print(f"     Verdict: {status}")
                if "feedback" in output_data:
                    print(f"       Feedback: {output_data['feedback']}")
            
            # 4. Fallback 
            else:
                print(f"   Raw Payload: {output_data}")

            print("-" * 100)
        
    print("\n" + "="*100)
    print("PROCESS COMPLETED")
    print("="*100)