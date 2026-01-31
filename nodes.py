import os
import json
import re
import glob
from langchain_core.messages import HumanMessage
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from state import AgentState, Resource, PlanSection
from model import llm
# [Refactor] We removed TavilyClient import because it is now encapsulated in tools.py
from docx import Document
from docx.shared import RGBColor
from logger import logger 
from tools import search_educational_resources # <--- Using the Standardized Tool

# --- Helper for Robust Parsing ---
def extract_json(text):
    """
    Extracts JSON content from raw LLM output.
    Handles triple backticks, plain JSON, and text-embedded JSON.
    """
    text = text.strip()
    match = re.search(r"```(json)?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(2).strip()
    start_index = text.find('{')
    end_index = text.rfind('}')
    if start_index != -1 and end_index != -1:
        return text[start_index : end_index + 1]
    return text


# --- ORCHESTRATOR (Router) ---
def topic_router_node(state: AgentState):
    logger.log_event("ROUTER", "START", "Analyzing Topic Intent")
    topic = state["topic"]
    
    prompt = f"""
    Analyze the study topic: '{topic}'
    Classify it into one of these two categories:
    1. 'TECHNICAL': Requires deep understanding of systems, mathematics, architecture, implementation, or specific tools.
    2. 'GENERAL': Focuses on concepts, history, sociology, ethics, or high-level overviews.
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


# --- Init Node ---
def init_node(state: AgentState):
    logger.log_event("INIT", "START", "Initializing Session")
    
    # Check if we already have a topic (e.g. passed from Graph or previous run)
    topic = state.get("topic", "")
    if not topic:
        topic = input("\n   What do you want to study? ").strip()
        if not topic: topic = "Agentic AI"
    
    if not os.path.exists("knowledge_base"): os.makedirs("knowledge_base")
    logger.log_event("INIT", "ACTION", f"Scanning 'knowledge_base' for '{topic}'...")

    files = glob.glob("knowledge_base/*")
    selected_files = state.get("syllabus", [])
    
    # Only ask for selection if not already selected (CLI mode)
    if files and not selected_files:
        print(f"   Found {len(files)} files:")
        for i, f in enumerate(files, 1):
            print(f"      [{i}] {os.path.basename(f)}")
        
        selection = input("      Selection (e.g. '1,2' or 'all'): ").strip().lower()
        if selection == 'all':
            selected_files = files
        elif selection not in ['none', '', 'no']:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(',')]
                selected_files = [files[i] for i in indices if 0 <= i < len(files)]
            except:
                logger.log_event("INIT", "ERROR", "Invalid selection.")

    logger.log_event("INIT", "RESULT", f"Topic: {topic}, Files: {len(selected_files)}")
    return {"topic": topic, "syllabus": selected_files} 


# --- Local Miner ---
def local_miner_node(state: AgentState):
    logger.log_event("MINER", "START", "Processing Local Files")    
    files = state.get("syllabus", [])
    local_resources = []
    
    if not files:
        logger.log_event("MINER", "INFO", "No local files selected.")
        return {"local_resources": []}
    
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
                logger.log_event("MINER", "ACTION", f"Summarizing {os.path.basename(file_path)}")
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
            logger.log_event("MINER", "ERROR", f"Failed to read {file_path}: {e}")

    logger.log_event("MINER", "RESULT", f"Extracted {len(local_resources)} local resources.")
    return {"local_resources": local_resources}


# --- Web Finder (The Worker) ---
def web_finder_node(state: AgentState):
    logger.log_event("FINDER", "START", "Executing Hierarchical Search")
    
    # [Theory] Hierarchical Execution (Slide 86)
    # The Worker executes the DAG nodes (Sections) created by the Manager.
    study_plan = state.get("study_plan", [])
    web_resources = []
    seen_urls = set()
    
    for section in study_plan:
        logger.log_event("FINDER", "THOUGHT", f"Working on Module: {section.section_title}")
        
        for query in section.queries:
            # 1. Execute Tool (Standardized)
            results = search_educational_resources.invoke(query)
            
            if isinstance(results, str): 
                logger.log_event("FINDER", "WARNING", f"Tool Error: {results}")
                continue
                
            # 2. Process Results
            found_in_query = False
            if results:
                for r in results:
                    url = r.get('url')
                    if url not in seen_urls:
                        
                        # Contextual Summary: The "Why" is now driven by the Section Description
                        sum_prompt = f"""
                        Context: We are studying '{state['topic']}'.
                        Current Module: '{section.section_title}' - {section.description}
                        
                        Source Content: {r.get('content', '')[:3000]}
                        
                        Task: Summarize how this source contributes to this specific module.
                        Keep it concise (3 bullets).
                        """
                        summary = llm.invoke([HumanMessage(content=sum_prompt)]).content.strip()

                        # Tag the title with the section for the final report
                        web_resources.append(Resource(
                            title=f"[{section.section_title}] {r.get('title')}", 
                            url=url,
                            summary=summary,
                            type="Web Source"
                        ))
                        seen_urls.add(url)
                        found_in_query = True
                        break # One good source per query is sufficient
            
            if not found_in_query:
                logger.log_event("FINDER", "INFO", "No unique source found for query.")
    
    return {"resources": web_resources}


# --- Judge Node ---
def judge_node(state: AgentState):
    logger.log_event("JUDGE", "START", "Starting Quality Control")
    local_res = state.get("local_resources", [])
    topic = state["topic"]
    
    if not local_res:
        logger.log_event("JUDGE", "INFO", "No local files to judge.")
        return {"is_approved": True} 

    logger.log_event("JUDGE", "THOUGHT", f"Reading {len(local_res)} documents against topic '{topic}'...")
    context = "\n".join([f"- {r.title}: {r.summary}" for r in local_res])
    
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
    

# --- SEARCH CRITIC ---
def search_critic_node(state: AgentState):
    logger.log_event("CRITIC", "START", "Validating Research")
    resources = state.get("resources", [])
    search_type = state.get("search_type", "general")
    retry = state.get("retry_count", 0) + 1
    
    if not resources:
        logger.log_event("CRITIC", "ACTION", "Empty results. Triggering retry.")
        return {"web_syllabus": [f"{state['topic']} guide", f"{state['topic']} documentation"], "retry_count": retry, "is_approved": False}

    logger.log_event("CRITIC", "THOUGHT", f"Evaluating quality against '{search_type}' standard...")    
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

        logger.log_event("CRITIC", "RESULT", f"Verdict: {'APPROVED' if approved else 'REJECTED'}. {critique}")

        if not approved and new_queries:
            print(f"   [Correction] Optimization: {new_queries}")
            return {
                "is_approved": False, 
                "retry_count": retry, 
                "web_syllabus": new_queries 
            }
        return {"is_approved": True, "feedback": critique}
    except Exception as e:
        logger.log_event("CRITIC", "ERROR", "Validation failed. Approving.")
        return {"is_approved": True}


# --- Human Review (HITL) ---
def human_review_node(state: AgentState):
    logger.log_event("HUMAN", "START", "Waiting for User Review")
    
    local_res = state.get("local_resources", [])
    judge_feedback = state.get("feedback", "No feedback")
    is_approved = state.get("is_approved", True)

    if not is_approved:
        logger.log_event("HUMAN", "THOUGHT", f"JUDGE WARNING: {judge_feedback}")
        print(f"     SYSTEM ALERT: The Judge flagged the local content: {judge_feedback}")
    
    if local_res:
        logger.log_event("HUMAN", "INFO", f"Processed {len(local_res)} local documents.")
    else:
        logger.log_event("HUMAN", "INFO", "No local knowledge found.")
        
    print(f"\n    Press [ENTER] to proceed with Web Research plan.")
    user_input = input("      Instructions/Adjustments: ").strip()
    
    if user_input:
        logger.log_event("HUMAN", "RESULT", f"User provided feedback: '{user_input}'")
        return {"feedback": user_input}
    else:
        logger.log_event("HUMAN", "RESULT", "User approved plan without changes.")
        return {"feedback": None}


# --- NEW: Web Planner (Tree of Thoughts Edition) ---
def web_planner_node(state: AgentState):
    logger.log_event("PLANNER", "START", "Tree of Thoughts: Generating Candidates")
    topic = state["topic"]
    search_type = state.get("search_type", "general")
    user_feedback = state.get("feedback")
    
    local_context = "\n".join([r.summary for r in state.get("local_resources", [])]) if state.get("local_resources") else "None"
    
    # [Theory] ToT Step 1: Branching (Generate Multiple Perspectives)
    # Instead of asking for 1 plan, we ask for 3 distinct approaches.
    prompt_branches = f"""
    You are a Study Architect. 
    Topic: {topic} ({search_type.upper()})
    User Feedback: {user_feedback if user_feedback else "None"}
    
    Step 1: Generate 3 DIFFERENT structural approaches (Candidates) for a study guide.
    
    - Candidate A: "Academic/Theoretical" (Focus on definitions, history, axioms)
    - Candidate B: "Practical/Applied" (Focus on usage, tools, real-world examples)
    - Candidate C: "Problem-Solving" (Focus on challenges, solutions, case studies)
    
    Return JSON:
    {{
      "candidates": [
        {{ "id": "A", "reasoning": "...", "plan": [ {{ "section_title": "...", "queries": [...] }} ] }},
        {{ "id": "B", "reasoning": "...", "plan": [...] }},
        {{ "id": "C", "reasoning": "...", "plan": [...] }}
      ]
    }}
    """
    
    # Generate branches
    response_branches = llm.invoke([HumanMessage(content=prompt_branches)])
    
    try:
        data = json.loads(extract_json(response_branches.content))
        candidates = data.get("candidates", [])
        logger.log_event("PLANNER", "THOUGHT", f"Generated {len(candidates)} candidate plans.")
    except:
        # Fallback if branching fails
        return {"study_plan": [PlanSection(section_title="General", description="Fallback", queries=[f"{topic} guide"])]}

    # [Theory] ToT Step 2: Evaluation & Selection (Pruning)
    # We now ask the LLM to act as the "Judge" and pick the best one for the user's specific intent.
    
    eval_prompt = f"""
    Topic: {topic}
    Intended Strategy: {search_type.upper()}
    User Feedback: {user_feedback}
    
    Review these 3 candidate plans:
    {json.dumps(candidates, indent=2)}
    
    Task:
    1. Evaluate which candidate best fits the Intended Strategy and User Feedback.
    2. If the user asked for "Technical", prioritize Practical/Problem-Solving.
    3. If the user asked for "General", prioritize Academic/Theoretical.
    
    Return JSON of the WINNING plan only:
    {{
      "selected_id": "B",
      "rationale": "Matches user request for code examples...",
      "plan": [ ... (the full plan from the chosen candidate) ... ]
    }}
    """
    
    logger.log_event("PLANNER", "THOUGHT", "Evaluator is reviewing candidates...")
    response_eval = llm.invoke([HumanMessage(content=eval_prompt)])
    
    study_plan = []
    try:
        selection_data = json.loads(extract_json(response_eval.content))
        selected_plan = selection_data.get("plan", [])
        rationale = selection_data.get("rationale", "No rationale")
        
        # Convert to Pydantic
        for item in selected_plan:
            study_plan.append(PlanSection(
                section_title=item['section_title'],
                description=item.get('description', 'Study this section'), # Robustness
                queries=item['queries']
            ))
            
        logger.log_event("PLANNER", "RESULT", f"Winner: Candidate {selection_data.get('selected_id')} | Reason: {rationale}")
        
    except Exception as e:
        logger.log_event("PLANNER", "ERROR", f"Selection failed: {e}")
        # Emergency Fallback: Just take the first candidate's plan
        raw_plan = candidates[0].get("plan", [])
        for item in raw_plan:
            study_plan.append(PlanSection(section_title=item['section_title'], description="Fallback", queries=item['queries']))

    return {"study_plan": study_plan}
 

# --- Publisher Node ---
def publisher_node(state: AgentState):
    logger.log_event("PUBLISHER", "START", "Compiling Document")
    topic = state["topic"]
    is_approved = state.get("is_approved", True)

    output_folder = "generated_plans"
    if not os.path.exists(output_folder): os.makedirs(output_folder)

    filename = f"{topic.replace(' ', '_')}_Study_Plan.docx"
    file_path = os.path.join(output_folder, filename)

    local_res = state.get("local_resources", [])
    web_res = state.get("resources", [])
    
    doc = Document()
    doc.add_heading(f'Study Plan: {topic}', 0)
    
    if local_res:
        doc.add_heading('Part 1: Local Library', 1)
        if not is_approved:
            p = doc.add_paragraph()
            run = p.add_run("WARNING: The Judge flagged these documents as potentially irrelevant to the topic.")
            run.font.color.rgb = RGBColor(255, 0, 0)
            run.bold = True

        for r in local_res:
            heading = doc.add_heading(level=2)
            run = heading.add_run(r.title)
            if not is_approved:
                run.font.color.rgb = RGBColor(255, 0, 0)
                run.text = f"{r.title} [FLAGGED]"
            doc.add_paragraph(r.summary)
            
    if web_res:
        doc.add_heading('Part 2: Web Research', 1)
        for r in web_res:
            doc.add_heading(f" {r.title}", 2)
            doc.add_paragraph(r.summary)
            doc.add_paragraph(f"Link: {r.url}")
        
    try:
        doc.save(file_path)
        logger.log_event("PUBLISHER", "RESULT", f"Saved to {file_path}")
        return {"final_file": file_path} 
    except Exception as e:
        logger.log_event("PUBLISHER", "ERROR", f"Save failed: {e}")
        return {}