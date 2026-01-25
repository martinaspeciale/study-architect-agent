import os
import json
import re
import glob
from langchain_core.messages import HumanMessage
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from state import AgentState, Resource
from model import llm
from tavily import TavilyClient
from docx import Document

# --- Helper for Robust Parsing ---
def extract_json(text):
    """Extracts JSON content from raw LLM output."""
    text = text.strip()
    match = re.search(r"```(json)?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(2)
    return text.strip()

# --- Visual Helper ---
def print_header(text):
    print(f"\n{f' --- {text} --- ':^100}")

# --- Planner Node ---
def planner_node(state: AgentState):
    retry = state.get('retry_count', 0) + 1
    print(f"\n --- PLANNER (Attempt {retry}) --- ".center(100))    
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
    print(f"\n{' --- FINDER (Tavily)  --- ':^100}")
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
    print(f"\n{' --- JUDGE --- ':^100}")
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
    except Exception as e:
        print(f"Judge Parsing Error: {e}")
        return {"is_approved": False, "feedback": "Judge parsing error"}
    


# --- Human Review Node (Human-in-the-Loop) ---
def human_review_node(state: AgentState):
    print(f"\n{' --- HUMAN REVIEW --- ':^100}")
    syllabus = state.get("syllabus", [])
    
    # 1. Display the current plan to the user
    print(f"   Proposed Plan for '{state['topic']}':")
    for i, module in enumerate(syllabus, 1):
        print(f"   {i}. {module}")
    
    print("-" * 100)
    
    # 2. Request user input
    print("   [ENTER] to approve and proceed to research.")
    print("   [Text] to request changes (e.g., 'Remove module 2', 'Add more focus on X').")
    user_input = input("   Your feedback: ").strip()
    
    # 3. Handle logic
    if user_input:
        print(f"   Requesting revision: '{user_input}'")
        # Update feedback for the Planner and signal that it is NOT approved
        return {"feedback": user_input} 
    else:
        print("   Plan approved by Human.")
        # Clear previous feedback and proceed
        return {"feedback": None}
    


# --- Publisher Node ---
def publisher_node(state: AgentState):
    print(f"\n{' --- PUBLISHER --- ':^100}")
    
    topic = state["topic"]
    filename = f"{topic.replace(' ', '_')}_Study_Plan.docx"
    
    # Create Document
    doc = Document()
    doc.add_heading(f'Study Plan: {topic}', 0)
    
    doc.add_heading('Syllabus', level=1)
    for i, module in enumerate(state.get("syllabus", []), 1):
        doc.add_paragraph(f"{i}. {module}", style='List Number')
        
    doc.add_heading('Curated Resources', level=1)
    resources = state.get("resources", [])
    
    if resources:
        for res in resources:
            p = doc.add_paragraph()
            p.add_run(f"{res.title}").bold = True
            p.add_run(f"\nLink: {res.url}")
    else:
        doc.add_paragraph("No resources found.")
        
    # Save file
    try:
        doc.save(filename)
        print(f"     Document saved: {filename}")
        return {"final_file": filename} 
    except Exception as e:
        print(f"     Error saving document: {e}")
        return {}