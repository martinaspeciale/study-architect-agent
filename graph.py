from langgraph.graph import StateGraph, END
from state import AgentState
from nodes import (
    init_node, 
    local_miner_node, 
    judge_node, 
    human_review_node, 
    web_planner_node, 
    web_finder_node, 
    publisher_node,
    search_critic_node,
    topic_router_node   
)

# Conditional Logic Helper
def check_critic_verdict(state: AgentState):
    # Stop infinite loops
    if state.get("retry_count", 0) >= 3:
        print("   [System] Max retries reached. Publishing best effort.")
        return "proceed"
    
    # Check if Critic approved
    if state.get("is_approved", True):
        return "proceed"
        
    # Otherwise loop back
    return "loop"

# --- Graph Construction ---
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("init", init_node)
workflow.add_node("local_miner", local_miner_node)
workflow.add_node("judge", judge_node)
workflow.add_node("human", human_review_node)
workflow.add_node("router", topic_router_node)
workflow.add_node("web_planner", web_planner_node)
workflow.add_node("web_finder", web_finder_node)
workflow.add_node("search_critic", search_critic_node) 
workflow.add_node("publisher", publisher_node)

# Set Entry
workflow.set_entry_point("init")

# Linear Phase
workflow.add_edge("init", "local_miner")
workflow.add_edge("local_miner", "judge")
workflow.add_edge("judge", "human")
workflow.add_edge("human", "router")       # Router decides strategy
workflow.add_edge("router", "web_planner") 
workflow.add_edge("web_planner", "web_finder")

# Self-Correction Loop
workflow.add_edge("web_finder", "search_critic") # Always check quality

workflow.add_conditional_edges(
    "search_critic",
    check_critic_verdict,
    {
        "proceed": "publisher",  # Good Quality -> Done
        "loop": "web_finder"     # Bad Quality  -> Search again
    }
)

workflow.add_edge("publisher", END)


app = workflow.compile()

if __name__ == "__main__":
    # Visual Separators
    MAIN_DIVIDER = "═" * 85
    SUB_DIVIDER  = "─" * 85
    
    print("\n" + MAIN_DIVIDER)
    print(f"{'MULTI-AGENT STUDY ARCHITECT':^85}")
    print(MAIN_DIVIDER)
    
    # Initialize with empty state (init_node will handle the inputs)
    initial_state = {
        "topic": "", 
        "retry_count": 0,
        "feedback": None,
        "is_approved": False,
        "syllabus": [],   
        "resources": [],
        "local_resources": [],
        "web_syllabus": []
    }
    
    # Start the graph
    for event in app.stream(initial_state):
        for node_name, output_data in event.items():
            if output_data is None: output_data = {}

            print(f"\n MESSAGE PASSING (From: {node_name.upper()})")
            print(SUB_DIVIDER)

            # 1. INIT (Shows topic selected)
            if node_name == "init":
                print(f"   Topic Set: {output_data.get('topic', 'Unknown')}")
                if output_data.get('syllabus'):
                    print(f"   Files Queued: {len(output_data['syllabus'])}")

            # 2. LOCAL MINER (Shows local findings)
            elif "local_resources" in output_data:
                resources = output_data['local_resources']
                print(f"   Local Documents Processed ({len(resources)}):")
                for res in resources:
                    print(f"     • {res.title}")
            
            # 3. JUDGE (Shows Validation)
            elif node_name == "judge":
                status = "APPROVED" if output_data.get("is_approved") else "WARNING"
                print(f"   Relevance Check: {status}")
                if output_data.get("feedback"):
                    print(f"   Feedback: {output_data['feedback']}")

            # 4. HUMAN REVIEW 
            elif node_name == "human":
                if output_data.get("feedback"):
                     print(f"   User Guidance: {output_data['feedback']}")
                else:
                     print(f"   User Action: Approved to proceed")

            # 5. WEB PLANNER (Shows search plan)
            elif "web_syllabus" in output_data:
                print("   Web Research Plan:")
                for i, item in enumerate(output_data['web_syllabus'], 1):
                    print(f"     {i}. {item}")

            # 6. WEB FINDER (Shows web results)
            elif node_name == "web_finder" and "resources" in output_data:
                print(f"   Web Resources Found ({len(output_data['resources'])}):")
                for res in output_data['resources']:
                    print(f"     • {res.title}")
                    print(f"       {res.url}")

            # 7. PUBLISHER 
            elif node_name == "publisher":
                print(f"   Action: Generating Study Guide...")
                if "final_file" in output_data:
                    print(f"   Status: SAVED TO DISK -> {output_data['final_file']}")           
            
            # Fallback 
            else:
                print(f"   Raw Payload: {output_data}")

            print(SUB_DIVIDER)
        
    print("\n" + MAIN_DIVIDER)
    print(f"{'PROCESS COMPLETED':^85}")
    print(MAIN_DIVIDER)