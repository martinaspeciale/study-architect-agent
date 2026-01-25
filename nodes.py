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
    print(f"\n{f' --- {text} --- ':^85}")

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

# --- Web Finder (Execute Search) ---
def web_finder_node(state: AgentState):
    print_header("WEB FINDER (Tavily)")
    # Note: We now use 'web_syllabus', which comes from the Web Planner node
    web_syllabus = state.get("web_syllabus", [])
    web_resources = []
    
    try:
        tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    except KeyError:
        print("Error: TAVILY_API_KEY missing in .env")
        return {"resources": []}
    
    try:
        for item in web_syllabus:
            print(f"   Searching for: '{item}'")
            # We search specifically for educational content
            response = tavily.search(query=f"{state['topic']} {item} educational", max_results=1, search_depth="advanced")
            
            if response.get('results'):
                r = response['results'][0]
                
                # Generate a short summary for the web resource using the LLM
                sum_prompt = f"Summarize this web content for a student: {r.get('content', '')[:3000]}"
                summary = llm.invoke([HumanMessage(content=sum_prompt)]).content.strip()
                
                web_resources.append(Resource(
                    title=r.get('title', item),
                    url=r.get('url', '#'),
                    summary=summary,
                    type="Web Source"
                ))
    except Exception as e:
        print(f"Tavily Error: {e}")
        
    print(f"   Found {len(web_resources)} web resources.")
    # We store these in 'resources' which the Publisher expects for the web section
    return {"resources": web_resources}

# --- Judge Node (Validate Local Relevance) ---
def judge_node(state: AgentState):
    print_header("JUDGE (Quality Control)")
    local_res = state.get("local_resources", [])
    topic = state["topic"]
    
    if not local_res:
        print("   [System] No local files to judge. Skipping validation.")
        return {"is_approved": True} 

    print(f"   [Thinking] Reading {len(local_res)} documents...")
    print(f"   [Thinking] Comparing content against topic: '{topic}'...")
    
    context = "\n".join([f"- {r.title}: {r.summary}" for r in local_res])
    
    # Ask for a specific critique and score
    prompt = f"""
    You are a critical academic judge. 
    Topic: {topic}
    Documents:
    {context}
    
    Task: 
    1. Score relevance from 0-100.
    2. Provide a 1-sentence critique explaining WHY.
    3. Verdict (Approved if score > 70).
    
    Return JSON: {{ "score": 85, "critique": "Files cover the basics well but miss advanced topics.", "approved": true }}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        data = json.loads(extract_json(response.content))
        score = data.get("score", 0)
        critique = data.get("critique", "No critique provided.")
        approved = data.get("approved", False)
        
        # --- INTERNAL MONOLOGUE PRINTS ---
        print(f"   [Evaluation] Relevance Score: {score}/100")
        print(f"   [Critique]   \"{critique}\"")
        
        status = "APPROVED" if approved else "FLAGGED"
        print(f"   [Verdict]    {status}")
        
        return {"is_approved": approved, "feedback": critique}
        
    except Exception as e:
        print(f"   [Error] Judge failed to parse: {e}")
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