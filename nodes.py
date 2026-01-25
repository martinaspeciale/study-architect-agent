import os
import json
import re
from langchain_core.messages import HumanMessage
from state import AgentState, Resource
from model import llm
from tavily import TavilyClient

# --- Helper for Robust Parsing ---
def extract_json(text):
    """Extracts JSON content from raw LLM output."""
    text = text.strip()
    match = re.search(r"```(json)?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(2)
    return text.strip()

# --- Planner Node ---
def planner_node(state: AgentState):
    retry = state.get('retry_count', 0) + 1
    print(f"\n--- PLANNER (Attempt {retry}) ---")
    
    prompt = f"""You are a Senior Academic Tutor.
    TOPIC: {state['topic']}
    FEEDBACK: {state.get('feedback', 'None')}
    
    Create a syllabus with 4 distinct modules.
    Return ONLY a JSON list of strings. Example: ["Module 1", "Module 2"]
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # Verbose Logging (Clean)
    # print(f"PLANNER RAW RESPONSE:\n{'-'*20}\n{response.content}\n{'-'*20}")
    
    try:
        content = extract_json(response.content)
        syllabus = json.loads(content)
    except Exception as e:
        print(f"Planner Parsing Error: {e}")
        syllabus = []
        
    return {"syllabus": syllabus, "retry_count": retry}

# --- Finder Node ---
def finder_node(state: AgentState):
    print("\n--- FINDER (Tavily) ---")
    syllabus = state.get("syllabus", [])
    resources = []
    
    # Initialize Client inside node to ensure env var is loaded
    try:
        tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    except KeyError:
        print("Error: TAVILY_API_KEY missing in .env")
        return {"resources": []}
    
    try:
        for module in syllabus:
            print(f"   Searching for: '{module}'")
            
            response = tavily.search(query=f"academic resources for {module}", max_results=1, search_depth="advanced")
            
            if response.get('results'):
                r = response['results'][0]
                print(f"   --> Found: {r.get('title')}")
                
                resources.append(Resource(
                    title=r.get('title', module),
                    url=r.get('url', '#'),
                    type="Web Source"
                ))
    except Exception as e:
        print(f"Tavily Error: {e}")
        
    print(f"   Total resources found: {len(resources)}")
    return {"resources": resources}

# --- Judge Node ---
def judge_node(state: AgentState):
    print("\n--- JUDGE ---")
    resources = state.get("resources", [])
    
    if not resources:
        return {"is_approved": False, "feedback": "No resources found via Tavily."}

    prompt = f"""Evaluate this study plan.
    Syllabus: {state['syllabus']}
    Resources Found: {len(resources)}
    
    Rules:
    1. Syllabus must have at least 3 items.
    2. Resources must be present.
    
    Return JSON ONLY: {{"approved": true, "feedback": "..."}}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])

    # Verbose Logging 
    # print(f"JUDGE RAW RESPONSE:\n{'-'*20}\n{response.content}\n{'-'*20}")
    
    try:
        content = extract_json(response.content)
        result = json.loads(content)
        
        status = "APPROVED" if result['approved'] else "REJECTED"
        print(f"   Decision: {status}")
        
        return {"is_approved": result["approved"], "feedback": result["feedback"]}
    except:
        return {"is_approved": False, "feedback": "Judge parsing error"}