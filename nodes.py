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
from docx.shared import RGBColor
from logger import logger 

# --- Helper for Robust Parsing ---
def extract_json(text):
    """
    Extracts JSON content from raw LLM output.
    Handles triple backticks, plain JSON, and text-embedded JSON.
    """
    text = text.strip()
    
    # Try to find markdown code blocks first
    match = re.search(r"```(json)?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(2).strip()
    
    # If no markdown, try to find the pure JSON object (start at '{' and end at '}')
    start_index = text.find('{')
    end_index = text.rfind('}')
    
    if start_index != -1 and end_index != -1:
        return text[start_index : end_index + 1]
    
    # Fallback: Return original text and hope it works
    return text


# --- ORCHESTRATOR (Router) ---
def topic_router_node(state: AgentState):
    logger.log_event("ROUTER", "START", "Analyzing Topic Intent")

    topic = state["topic"]
    
    # We use the LLM to decide based on nuance, not just keywords
    prompt = f"""
    Analyze the study topic: '{topic}'
    
    Classify it into one of these two categories:
    
    1. 'TECHNICAL': Requires deep understanding of systems, mathematics, architecture, implementation, or specific tools.
       (Examples: "Transformer Architecture", "Gradient Descent", "Kubernetes Patterns", "Python AsyncIO")
       
    2. 'GENERAL': Focuses on concepts, history, sociology, ethics, or high-level overviews.
       (Examples: "History of AI", "Impact of Social Media", "Introduction to Economics", "AI Ethics")
    
    Return JSON ONLY: {{"type": "TECHNICAL"}} or {{"type": "GENERAL"}}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        data = json.loads(extract_json(response.content))
        search_type = data.get("type", "GENERAL").lower()
    except:
        search_type = "general"

    logger.log_event("ROUTER", "RESULT", f"Routing to '{search_type.upper()}' strategy.", metadata={"type": search_type})

    return {"search_type": search_type}

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
    web_syllabus = state.get("web_syllabus", [])
    web_resources = []
    seen_urls = set()
    
    try:
        tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    except:
        print("   [Error] API Key missing.")
        return {"resources": []}
    
    for item in web_syllabus:
        print(f"\n    Query: '{item}'")
        try:
            response = tavily.search(query=f"{state['topic']} {item} educational", max_results=5, search_depth="advanced")
            
            found_new_source = False
            if response.get('results'):
                for r in response['results']:
                    url = r.get('url')
                    title = r.get('title')
                    
                    if url not in seen_urls: # <--- CHECK: Have we used this yet?
                        # Found a unique source! Process it.
                        print(f"      --> Found: {title}")
                        print(f"      --> Link:  {url}")
                        print(f"      [Reading]  Summarizing content...")
                        
                        sum_prompt = f"Summarize this for a student in 3 bullet points: {r.get('content', '')[:3000]}"
                        summary = llm.invoke([HumanMessage(content=sum_prompt)]).content.strip()

                        web_resources.append(Resource(
                            title=title,
                            url=url,
                            summary=summary,
                            type="Web Source"
                        ))

                        seen_urls.add(url) # <- Don't use this URL again
                        found_new_source = True
                        break # stop looking for this query, move to next item

                if not found_new_source:
                    print("      [Result] Only duplicate sources found. Skipping.")
            else:
                print("      [Result] No good results found.")
                
        except Exception as e:
            print(f"      [Error] {e}")

    print(f"\n    Research Complete. Handing off {len(web_resources)} items to Publisher.")
    return {"resources": web_resources}

# --- Judge Node (Validate Local Relevance) ---
def judge_node(state: AgentState):
    logger.log_event("JUDGE", "START", "Starting Quality Control")

    local_res = state.get("local_resources", [])
    topic = state["topic"]
    
    if not local_res:
        logger.log_event("JUDGE", "INFO", "No local files to judge.")
        return {"is_approved": True} 

    logger.log_event("JUDGE", "THOUGHT", f"Reading {len(local_res)} documents against topic '{topic}'...")

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
        
        logger.log_event("JUDGE", "RESULT", f"Score: {score}/100 - {critique}", metadata={"score": score, "approved": approved})
        
        return {"is_approved": approved, "feedback": critique}
        
    except Exception as e:
        logger.log_event("JUDGE", "ERROR", f"Failed to parse: {e}")
        return {"is_approved": True}
    
# --- SEARCH CRITIC (Quality Gatekeeper) ---
# Implements "Agent-as-a-Judge" 
def search_critic_node(state: AgentState):
    print_header("SEARCH CRITIC (Quality Control)")
    
    resources = state.get("resources", [])
    search_type = state.get("search_type", "general")
    retry = state.get("retry_count", 0) + 1
    
    # 1. If no resources found at all, we MUST retry (Legacy safety net)
    if not resources:
        print("   [Critique] No resources found. Triggering blind retry.")
        return {"web_syllabus": [f"{state['topic']} guide", f"{state['topic']} documentation"], "retry_count": retry, "is_approved": False}

    # 2. Evaluate Quality of Found Resources
    print(f"   [Analysis] Evaluating {len(resources)} resources against '{search_type.upper()}' standard...")
    
    context = "\n".join([f"- Title: {r.title}\n  Summary: {r.summary}" for r in resources])
    
    prompt = f"""
    You are a Research Critic.
    Topic: {state['topic']}
    Strategy: {search_type.upper()} (User expects {search_type} depth)
    
    Found Resources:
    {context}
    
    Task:
    1. Are these resources sufficient and relevant?
    2. If Strategy is TECHNICAL, do they mention code, architecture, or implementation?
    3. If Strategy is GENERAL, do they cover concepts clearly?
    
    Return JSON ONLY:
    {{
        "approved": true,
        "critique": "Resources are relevant."
    }}
    OR
    {{
        "approved": false,
        "critique": "Resources are too superficial. We need more implementation details.",
        "better_queries": ["python implementation of {state['topic']}", "{state['topic']} github code"]
    }}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        data = json.loads(extract_json(response.content))
        approved = data.get("approved", False)
        critique = data.get("critique", "Unknown quality issue.")
        new_queries = data.get("better_queries", [])
        
        print(f"   [Verdict]  {' APPROVED' if approved else ' REJECTED'}")
        print(f"   [Feedback] {critique}")
        
        if not approved and new_queries:
            print(f"   [Correction] Optimization: {new_queries}")
            return {
                "is_approved": False, 
                "retry_count": retry, 
                "web_syllabus": new_queries # Overwrite plan with better queries
            }
            
        return {"is_approved": True, "feedback": critique}
        
    except Exception as e:
        print(f"   [Error] Critic failed ({e}). Defaulting to approval.")
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

# --- Web Planner (Gap Analysis & Reasoning) ---
def web_planner_node(state: AgentState):
    print_header("WEB PLANNER")
    topic = state["topic"]
    local_res = state.get("local_resources", [])
    
    print(f"   [Goal] Identify knowledge gaps for '{topic}'.")
    
    local_context = "Nothing."
    if local_res:
        local_context = "\n".join([r.summary for r in local_res])
        print(f"   [Memory] specific knowledge found in {len(local_res)} local files.")
    else:
        print("   [Memory] No local context available. Starting fresh.")

    prompt = f"""
    Topic: {topic}
    Local Knowledge: {local_context}
    
    Task:
    1. List 3 concepts MISSING from the local knowledge.
    2. Convert these into 3 search queries.
    
    Return JSON list: ["query 1", "query 2", "query 3"]
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        web_syllabus = json.loads(extract_json(response.content))
        print(f"   [Gap Analysis] Local files missed these key areas:")
        for item in web_syllabus:
            print(f"       Needs external research: '{item}'")
            
    except:
        web_syllabus = [f"{topic} core concepts", f"{topic} examples", f"{topic} advanced theory"]
        print("   [Fallback] Using default search strategy.")
        
    return {"web_syllabus": web_syllabus}


# --- Publisher Node ---
def publisher_node(state: AgentState):
    print_header("PUBLISHER")

    topic = state["topic"]
    # Check if the Judge approved the local content
    is_approved = state.get("is_approved", True)

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

        # Add a warning note if the judge flagged them
        if not is_approved:
            p = doc.add_paragraph()
            run = p.add_run("WARNING: The Judge flagged these documents as potentially irrelevant to the topic.")
            run.font.color.rgb = RGBColor(255, 0, 0) # Red
            run.bold = True

        for r in local_res:
            # We create an empty heading first, then add the text 'run' to color it
            heading = doc.add_heading(level=2)
            run = heading.add_run(r.title)
            
            # If not approved, turn the title RED
            if not is_approved:
                run.font.color.rgb = RGBColor(255, 0, 0) # Red
                run.text = f"{r.title} [FLAGGED]"

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