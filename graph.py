from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import planner_node, finder_node, judge_node, human_review_node, publisher_node

# --- Router Logic ---
def human_router(state: AgentState):
    """Decides whether to go back to Planner (changes requested) or Finder (approved)."""
    # If there is feedback in the last step, the user requested changes
    if state.get("feedback"):
        return "retry"
    # Otherwise proceed
    return "proceed"

def quality_router(state: AgentState):
    """The standard quality check router (Circuit Breaker)."""
    if state["retry_count"] > 4:
        return "end"
    if state["is_approved"]:
        return "continue" # SUCCESS -> Go to Publisher 
    return "retry"


# --- Graph Construction ---
workflow = StateGraph(AgentState)

workflow.add_node("planner", planner_node)
workflow.add_node("human", human_review_node) # ADDED THIS NODE
workflow.add_node("finder", finder_node)
workflow.add_node("judge", judge_node)
workflow.add_node("publisher", publisher_node)

workflow.set_entry_point("planner")

# Planner -> Human (User sees the draft first)
workflow.add_edge("planner", "human")

# Human -> ? (Conditional Branch)
workflow.add_conditional_edges(
    "human",
    human_router,
    {
        "retry": "planner", # User requested changes -> Plan again
        "proceed": "finder" # User approved -> Search resources
    }
)

# Finder -> Judge
workflow.add_edge("finder", "judge")

# Judge -> ? (Quality Conditional Branch)
workflow.add_conditional_edges(
    "judge",
    quality_router,
    {
        "continue": "publisher",    # Approved -> Make Doc
        "retry": "planner",         # Rejected -> Plan again
        "end": END                  # Failed   -> Stop
    }
)

# Publisher -> END
workflow.add_edge("publisher", END)

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
            if output_data is None:
                output_data = {}

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
            
            # 4. HUMAN REVIEW 
            elif node_name == "human":
                if output_data.get("feedback"):
                     print(f"     Status: REVISION REQUESTED")
                     print(f"     User Feedback: {output_data['feedback']}")
                else:
                     print(f"     Status: APPROVED BY USER") 

            # 5. PUBLISHER 
            elif node_name == "publisher":
                print(f"     Action: Generating Study Guide...")
                print(f"     Status: SAVED TO DISK (.docx)")           
            
            # 6. Fallback 
            else:
                print(f"   Raw Payload: {output_data}")

            print("-" * 100)
        
    print("\n" + "="*100)
    print("PROCESS COMPLETED")
    print("="*100)