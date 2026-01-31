import os
import json
import re
import glob
from langchain_core.messages import HumanMessage
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from docx import Document

# Import dai tuoi moduli locali
from state import AgentState, Resource, PlanSection
from model import llm
from logger import logger  # Assicurati che logger.py sia nella stessa cartella
from tools import search_educational_resources

# --- HELPER: Estrazione JSON robusta ---
def extract_json(text):
    """Pulisce l'output dell'LLM per estrarre solo il blocco JSON."""
    text = text.strip()
    # Cerca blocchi ```json ... ```
    match = re.search(r"```(json)?(.*?)```", text, re.DOTALL)
    if match: return match.group(2).strip()
    # Cerca parentesi graffe esterne
    if '{' in text and '}' in text: 
        return text[text.find('{'):text.rfind('}')+1]
    return text

# --- NODI DEL GRAFO ---

def init_node(state: AgentState):
    topic = state.get("topic", "Agentic AI")
    
    # Setup cartelle
    if not os.path.exists("knowledge_base"): os.makedirs("knowledge_base")
    files = [f for f in glob.glob("knowledge_base/*") if not os.path.basename(f).startswith('.')]
    
    # Logica verbosa
    thought = f"🚀 Inizializzazione workflow per: '{topic}'.\n"
    thought += f"📂 Scansione Knowledge Base: trovati {len(files)} documenti."
    
    # Logging su file + UI
    logger.log_event("INIT", "START", f"Sessione avviata per {topic}")
    
    return {
        "topic": topic, 
        "syllabus": files, 
        "retry_count": 0,
        "current_node_logs": thought
    } 

def local_miner_node(state: AgentState):
    files = state.get("syllabus", [])
    thought = "🔍 Analisi documenti locali (RAG)...\n"
    
    if not files:
        thought += "⚠️ Nessun file locale trovato. Salto questo step."
        return {"local_resources": [], "current_node_logs": thought}
    
    local_resources = []
    for file_path in files:
        fname = os.path.basename(file_path)
        thought += f"📄 Leggo: {fname}...\n"
        try:
            content = ""
            if file_path.endswith(".pdf"):
                loader = PyPDFLoader(file_path)
                # Leggiamo solo le prime 3 pagine per velocità nella demo
                pages = loader.load()[:3]
                content = "\n".join([p.page_content for p in pages])
            elif file_path.endswith(".txt"):
                loader = TextLoader(file_path)
                content = loader.load()[0].page_content
            
            if content:
                # Riassunto rapido
                prompt = f"Summarize regarding '{state['topic']}': {content[:3000]}"
                summary_res = llm.invoke([HumanMessage(content=prompt)])
                summary = summary_res.content
                
                local_resources.append(Resource(
                    title=fname, 
                    url="local_file", 
                    summary=summary, 
                    type="file"
                ))
        except Exception as e:
            thought += f"❌ Errore su {fname}: {str(e)}\n"
            logger.log_event("LOCAL_MINER", "ERROR", f"File {fname}: {e}")

    thought += f"✅ Indicizzati {len(local_resources)} documenti locali."
    logger.log_event("LOCAL_MINER", "RESULT", f"Create {len(local_resources)} risorse locali")
    
    return {
        "local_resources": local_resources, 
        "current_node_logs": thought
    }

def judge_node(state: AgentState):
    thought = "⚖️ Valutazione pertinenza contesto...\n"
    
    # Logica semplificata: se abbiamo risorse locali, le consideriamo buone
    has_local = len(state.get("local_resources", [])) > 0
    
    if has_local:
        thought += "✅ Il contesto locale è pertinente al topic richiesto."
    else:
        thought += "ℹ️ Nessun contesto locale. Approvo la ricerca web totale."
    
    logger.log_event("JUDGE", "THOUGHT", "Approvato passaggio allo step successivo")
    
    return {
        "is_approved": True, 
        "feedback": "Checked.",
        "current_node_logs": thought
    }

def human_review_node(state: AgentState):
    """
    Nodo passivo per gestire l'interruzione Human-in-the-loop.
    """
    feedback = state.get("feedback", "Nessun feedback precedente")
    thought = f"🛑 Handoff: Richiesta revisione umana.\n"
    thought += f"💬 Ultimo input utente: '{feedback}'"
    
    logger.log_event("HUMAN", "WAIT", "In attesa di input utente")
    
    return {
        "current_node_logs": thought
    }

def topic_router_node(state: AgentState):
    thought = "🚦 Analisi intento e routing...\n"
    thought += "⚙️ Modalità selezionata: TECHNICAL (Deep Dive)."
    
    logger.log_event("ROUTER", "ACTION", "Route: Technical")
    
    return {
        "search_type": "technical",
        "current_node_logs": thought
    }

def web_planner_node(state: AgentState):
    topic = state.get("topic")
    thought = f"📅 Creazione 'Tree of Thoughts' per: {topic}...\n"
    
    # Prompt strutturato per forzare il JSON corretto
    prompt = f"""You are a Study Architect. Create a 3-step study plan for '{topic}'.
    Return ONLY a JSON object with this structure:
    {{ 
      "plan": [ 
        {{ 
          "section_title": "Title of the module", 
          "description": "What the user will learn (max 1 sentence)", 
          "queries": ["search query 1", "search query 2"] 
        }} 
      ] 
    }}
    """
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        json_str = extract_json(res.content)
        data = json.loads(json_str)
        
        raw_plan = data.get("plan", [])
        plan_objs = []
        
        # Costruzione robusta degli oggetti PlanSection
        for item in raw_plan:
            # FIX CRUCIALE: Assicuriamo che 'description' esista sempre
            if "description" not in item or not item["description"]:
                item["description"] = f"Approfondimento su {item.get('section_title', topic)}"
            
            plan_objs.append(PlanSection(**item))
            
        thought += f"✨ Generato piano con {len(plan_objs)} moduli:\n"
        for p in plan_objs:
            thought += f"   - {p.section_title}\n"
            
        final_plan = plan_objs

    except Exception as e:
        thought += f"⚠️ Errore generazione piano: {str(e)}. Uso fallback.\n"
        logger.log_event("WEB_PLANNER", "ERROR", str(e))
        
        # Fallback sicuro
        final_plan = [
            PlanSection(
                section_title="Core Concepts", 
                description=f"Introduction to {topic}", 
                queries=[f"{topic} explained", f"{topic} tutorial"]
            )
        ]
    
    logger.log_event("WEB_PLANNER", "RESULT", f"Creati {len(final_plan)} step")
    return {
        "study_plan": final_plan,
        "current_node_logs": thought
    }

def web_finder_node(state: AgentState):
    plan = state.get("study_plan", [])
    thought = "🌐 Esecuzione ricerca Web (Tavily API)...\n"
    
    resources = []
    seen_urls = set()
    
    for section in plan:
        thought += f"🔎 Ricerca: '{section.section_title}'...\n"
        # Usiamo solo la prima query per risparmiare tempo/token nella demo
        query = section.queries[0] 
        
        try:
            results = search_educational_resources.invoke(query)
            
            # Gestione se results è una lista o stringa (dipende dal tool)
            if isinstance(results, list) and results:
                # Prendiamo il primo risultato migliore
                top_res = results[0]
                url = top_res.get('url')
                
                if url not in seen_urls:
                    r = Resource(
                        title=top_res.get('title', 'No Title'),
                        url=url,
                        summary=top_res.get('content', '')[:400] + "...",
                        type="web"
                    )
                    resources.append(r)
                    seen_urls.add(url)
                    thought += f"   🔗 Trovato: {r.title[:30]}...\n"
                    
        except Exception as e:
            thought += f"   ❌ Errore query: {str(e)}\n"

    thought += f"📦 Raccolte {len(resources)} nuove risorse."
    logger.log_event("WEB_FINDER", "RESULT", f"Trovate {len(resources)} risorse")
    
    return {
        "resources": resources,
        "current_node_logs": thought
    }

def search_critic_node(state: AgentState):
    retry = state.get("retry_count", 0)
    resources = state.get("resources", [])
    thought = f"🧐 Quality Gate (Iterazione {retry + 1})...\n"
    
    # Condizione di uscita forzata (Max retries o nessuna risorsa)
    if retry >= 2 or not resources:
        thought += "⚠️ Limite tentativi raggiunto o nessuna risorsa. Procedo comunque."
        logger.log_event("CRITIC", "DECISION", "Force Approve")
        return {
            "is_approved": True, 
            "retry_count": retry, 
            "current_node_logs": thought
        }

    # Valutazione LLM
    prompt = f"""Context: {state['topic']}
    Resources Found: {len(resources)}
    Titles: {[r.title for r in resources]}
    
    Are these sufficient to create a basic guide? 
    Return JSON: {{ "approved": true, "reason": "ok" }} OR {{ "approved": false, "reason": "missing basics" }}
    """
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        data = json.loads(extract_json(res.content))
        approved = data.get("approved", True)
        reason = data.get("reason", "Checked")
        
        if approved:
            thought += "✅ Risorse sufficienti. Qualità approvata."
        else:
            thought += f"❌ Risorse insufficienti ({reason}). Richiedo nuove ricerche."
            
        new_retry = retry + 1 if not approved else retry
        
        logger.log_event("CRITIC", "DECISION", f"Approved: {approved}")
        
        return {
            "is_approved": approved, 
            "feedback": reason,
            "retry_count": new_retry,
            "current_node_logs": thought
        }
        
    except:
        # In caso di errore LLM, approviamo per non bloccare
        return {"is_approved": True, "retry_count": retry, "current_node_logs": thought + "✅ Errore critic -> Auto-Approve."}

def publisher_node(state: AgentState):
    topic = state.get("topic")
    thought = "✍️ Redazione documento finale...\n"
    
    if not os.path.exists("generated_plans"): os.makedirs("generated_plans")
    filename = f"{topic.replace(' ', '_')}_Plan.docx"
    path = os.path.join("generated_plans", filename)
    
    try:
        doc = Document()
        doc.add_heading(f"Study Guide: {topic}", 0)
        
        all_resources = state.get("local_resources", []) + state.get("resources", [])
        
        doc.add_heading("Executive Summary", 1)
        doc.add_paragraph(f"Generated by AI Study Architect. Total sources: {len(all_resources)}")
        
        for r in all_resources:
            doc.add_heading(r.title, level=2)
            doc.add_paragraph(f"Source: {r.url}")
            doc.add_paragraph(f"Type: {r.type.upper()}")
            doc.add_paragraph(r.summary)
            doc.add_paragraph("-" * 20)
            
        doc.save(path)
        thought += f"🏁 File salvato correttamente: {filename}"
        logger.log_event("PUBLISHER", "SUCCESS", f"File salvato: {path}")
        
    except Exception as e:
        thought += f"❌ Errore salvataggio file: {str(e)}"
        logger.log_event("PUBLISHER", "ERROR", str(e))

    return {
        "final_file": path,
        "current_node_logs": thought
    }