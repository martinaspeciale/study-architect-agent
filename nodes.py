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
# --- Init Node (User Input + File Selection) ---
def init_node(state: AgentState):
    print_header("INITIALIZATION")
    
    topic = input("\n   What do you want to study? ").strip()
    if not topic: topic = "Agentic AI"
    
    # Crea cartella se non esiste
    if not os.path.exists("knowledge_base"): os.makedirs("knowledge_base")
    
    print(f"\n    Scanning 'knowledge_base' folder for resources on '{topic}'...")
    files = glob.glob("knowledge_base/*")
    selected_files = []
    
    if files:
        print(f"   Found {len(files)} files:")
        for i, f in enumerate(files, 1):
            print(f"      [{i}] {os.path.basename(f)}")
        
        print("\n    Select files to include (e.g., '1,3', 'all', 'none'):")
        selection = input("      Selection: ").strip().lower()
        
        if selection == 'all':
            selected_files = files
        elif selection not in ['none', '', 'no']:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                selected_files = [files[i] for i in indices if 0 <= i < len(files)]
            except:
                print("       Invalid selection. Proceeding with NO local files.")
    else:
        print("   (No local files found)")

    # Passiamo i percorsi dei file temporaneamente in 'syllabus'
    return {"topic": topic, "syllabus": selected_files} 

# --- Local Miner (Extract & Summarize) ---
def local_miner_node(state: AgentState):
    print_header("LOCAL MINER")
    files = state.get("syllabus", [])
    local_resources = []
    
    if not files:
        print("   No local files selected. Skipping to Web Planner.")
        return {"local_resources": []}

    print(f"    Analyzing {len(files)} local document(s)...")
    
    for file_path in files:
        try:
            content = ""
            if file_path.lower().endswith(".pdf"):
                loader = PyPDFLoader(file_path)
                content = "\n".join([p.page_content for p in loader.load()])
            elif file_path.lower().endswith(".docx"):
                loader = Docx2txtLoader(file_path)
                content = loader.load()[0].page_content
            
            if content:
                print(f"   --> Processing: {os.path.basename(file_path)}")
                
                # Semplice riassunto
                prompt = f"""
                Analyze this document: {os.path.basename(file_path)}
                Content Snippet: {content[:5000]}
                
                Task: Create a clear 3-bullet point summary of what this document teaches regarding '{state['topic']}'.
                """
                summary = llm.invoke([HumanMessage(content=prompt)]).content.strip()
                
                local_resources.append(Resource(
                    title=f"[FILE] {os.path.basename(file_path)}",
                    url=f"file://{file_path}",
                    summary=summary,
                    type="Local Document"
                ))
        except Exception as e:
            print(f"    Error reading {file_path}: {e}")

    return {"local_resources": local_resources}

# --- Finder Node ---
def finder_node(state: AgentState):
    print_header("FINDER (Tavily)")
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


# --- Judge Node (Validate Local Relevance) ---
def judge_node(state: AgentState):
    print_header("JUDGE (Quality Control)")
    local_res = state.get("local_resources", [])
    topic = state["topic"]
    
    if not local_res:
        print("   Info: No local resources to validate. Skipping.")
        return {"is_approved": True} # Passa oltre se non ci sono file

    print(f"    Validating relevance of {len(local_res)} documents against topic '{topic}'...")
    
    # Creiamo un contesto dai riassunti
    context = "\n".join([f"- {r.title}: {r.summary}" for r in local_res])
    
    prompt = f"""
    You are a Strict Academic Judge.
    Topic: {topic}
    Local Documents Found:
    {context}
    
    Task: specificy if these documents are relevant to the topic.
    If a document is completely off-topic (e.g., a cooking recipe for a Physics topic), mention it.
    
    Return JSON: {{"approved": true, "feedback": "All docs are relevant"}} 
    OR {{"approved": false, "feedback": "Doc X seems irrelevant because..."}}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        content = extract_json(response.content)
        result = json.loads(content)
        status = "APPROVED" if result['approved'] else "WARNING ISSUED"
        
        print(f"   Verdict: {status}")
        print(f"   Feedback: {result['feedback']}")
        
        # Salviamo il feedback nello stato per mostrarlo all'utente dopo
        return {"is_approved": result["approved"], "feedback": result["feedback"]}
        
    except Exception as e:
        print(f"   Judge Error: {e}")
        return {"is_approved": True}


# --- Human Review (HITL: Check Local Info + Judge Feedback) ---
def human_review_node(state: AgentState):
    print_header("HUMAN REVIEW")
    local_res = state.get("local_resources", [])
    judge_feedback = state.get("feedback", "No feedback")
    
    # Mostra avvisi del Judge se ce ne sono
    if state.get("is_approved") is False:
        print(f"    JUDGE WARNING: {judge_feedback}")
    
    if local_res:
        print(f"    Processed {len(local_res)} local documents.")
        # ... (stesso codice precedente)
    else:
        print("    No local knowledge found.")
        
    print("\n    Press [ENTER] to proceed with Web Research plan.")
    user_input = input("   Instructions/Adjustments: ").strip()
    
    # Puliamo il feedback del judge per non confondere il Planner dopo
    return {"feedback": user_input if user_input else None}

# --- Web Planner (Gap Analysis) ---
def web_planner_node(state: AgentState):
    print_header("WEB PLANNER")
    topic = state["topic"]
    local_res = state.get("local_resources", [])
    user_feedback = state.get("feedback", "")
    
    # Create context from local files
    local_context = "\n".join([r.summary for r in local_res])
    
    prompt = f"""
    Topic: {topic}
    User Feedback: {user_feedback}
    Context from Local Files: {local_context}
    
    Task: Identify 3 VITAL sub-topics MISSING from the local files.
    Return JSON list ONLY: ["Web Topic 1", "Web Topic 2", "Web Topic 3"]
    """
    
    print("    Analyzing gaps...")
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        web_syllabus = json.loads(extract_json(response.content))
        print(f"    Web Plan: {web_syllabus}")
    except:
        web_syllabus = [f"{topic} key concepts", f"{topic} advanced examples"]
        
    return {"web_syllabus": web_syllabus}
    


# --- Publisher Node ---
def publisher_node(state: AgentState):
    print_header("PUBLISHER")

    topic = state["topic"]

    output_folder = "generated_plans"
    if not os.path.exists(output_folder): os.makedirs(output_folder)

    filename = f"{topic.replace(' ', '_')}_Study_Plan.docx"
    file_path = os.path.join(output_folder, filename)

    local_res = state.get("local_resources", [])
    web_res = state.get("resources", [])
    
    # Create Document
    doc = Document()
    doc.add_heading(f'Study Plan: {topic}', 0)
    
    if local_res:
        doc.add_heading('Part 1: Local Library', 1)
        for r in local_res:
            doc.add_heading(r.title, 2)
            doc.add_paragraph(r.summary)
            
    if web_res:
        doc.add_heading('Part 2: Web Research', 1)
        for r in web_res:
            doc.add_heading(f" {r.title}", 2)
            doc.add_paragraph(r.summary)
            doc.add_paragraph(f"Link: {r.url}")
        
    # Save file
    try:
        doc.save(file_path)
        print(f"     Document saved: {file_path}")
        return {"final_file": file_path} 
    except Exception as e:
        print(f"     Error saving document: {e}")
        return {}