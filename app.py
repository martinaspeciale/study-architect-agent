import streamlit as st
import json
import os
import glob
import time 
from graph import app

st.set_page_config(page_title="Study Architect Feed", layout="wide", page_icon="🎓")

# --- CSS: Stile Dashboard e Log ---
st.markdown("""
<style>
    /* Dashboard Cards */
    div[data-testid="stMetric"] {
        background-color: #1e1e1e;
        border: 1px solid #333;
        padding: 10px;
        border-radius: 8px;
    }
    /* LIVE MODE: Green Pulse */
    .active-agent {
        border: 2px solid #00ff00 !important;
        background-color: #1b3a1b !important;
        box-shadow: 0 0 15px rgba(0, 255, 0, 0.4);
        color: #ffffff;
        transform: scale(1.05);
        font-weight: bold;
    }
    /* REPLAY MODE: Amber */
    .replay-agent {
        border: 2px solid #ffcc00 !important;
        background-color: #3a3a00 !important;
        box-shadow: 0 0 15px rgba(255, 204, 0, 0.4);
        color: #ffffff;
        transform: scale(1.05);
        font-weight: bold;
    }
    .inactive-agent {
        opacity: 0.3;
        border: 1px solid #444;
        background-color: #0e0e0e;
        filter: grayscale(100%);
    }
    
    /* Log Card Styling */
    .log-container {
        border-left: 3px solid #444;
        padding-left: 15px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎓 Agentic Study Architect: Live Feed")

# --- Session State ---
if "logs" not in st.session_state:
    st.session_state.logs = []
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Mission Control")
    topic = st.text_input("Argomento:", "Agentic AI")
    
    if not os.path.exists("knowledge_base"): os.makedirs("knowledge_base")
    kb_files = glob.glob("knowledge_base/*")
    file_names = [os.path.basename(f) for f in kb_files]
    
    selected_names = st.multiselect("Knowledge Base:", file_names)
    selected_paths = [os.path.join("knowledge_base", name) for name in selected_names]
    
    run_btn = st.button("🚀 Avvia Missione", type="primary")
    
    if os.path.exists("agent_trace.jsonl") and not st.session_state.logs:
        st.markdown("---")
        if st.button("📂 Ricarica Ultima Storia"):
            if os.path.exists("agent_trace.jsonl"):
                with open("agent_trace.jsonl", "r") as f:
                    st.session_state.logs = [json.loads(line) for line in f.readlines()]

config = {"configurable": {"thread_id": "1"}}

# --- DASHBOARD (Semafori) ---
agents_list = ["INIT", "MINER", "JUDGE", "PLANNER", "FINDER", "CRITIC", "PUBLISHER"]
cols = st.columns(len(agents_list))
placeholders = {agent: cols[idx].empty() for idx, agent in enumerate(agents_list)}

def render_dashboard(active_node_raw, mode="live"):
    node_map = {
        "init": "INIT", "local_miner": "MINER", "judge": "JUDGE",
        "web_planner": "PLANNER", "web_finder": "FINDER", 
        "search_critic": "CRITIC", "publisher": "PUBLISHER",
        "human": "JUDGE" 
    }
    active_agent = node_map.get(active_node_raw, active_node_raw.upper())

    for agent in agents_list:
        is_active = (agent == active_agent)
        style_class = "active-agent" if mode == "live" else "replay-agent"
        icon = "🟢 LIVE" if mode == "live" else "⏪ REPLAY"
        
        if not is_active:
            style_class = "inactive-agent"
            icon = "⚪"
        
        placeholders[agent].markdown(f"""
        <div class="{style_class}" style="text-align: center; padding: 10px; border-radius: 8px; transition: all 0.2s;">
            <small>{agent}</small><br><span style="font-size:1.1em;">{icon}</span>
        </div>
        """, unsafe_allow_html=True)

if not st.session_state.is_running:
    render_dashboard("NONE")

# --- AREA LOG (Placeholder Dinamico) ---
st.markdown("---")
feed_container = st.empty()

# --- HELPER: SLOW TYPING EFFECT ---
def stream_text(placeholder, text, prefix="", speed=0.1):
    """Simula la scrittura a macchina. Speed regola la velocità."""
    full_text = prefix
    for char in text:
        full_text += char
        placeholder.markdown(full_text + "▌") 
        time.sleep(speed)
    placeholder.markdown(full_text) 

def render_log_card(log_entry, animate=False):
    """Renderizza un log con animazione per TUTTI i tipi di eventi"""
    event = log_entry.get('event', 'INFO')
    agent = log_entry.get('agent', 'SYSTEM')
    content = log_entry.get('content', '')
    
    if event == "THOUGHT": icon, label = "🧠", f"{agent} Thinking"
    elif event == "ACTION": icon, label = "⚡", f"{agent} Action"
    elif event == "Result" or event == "RESULT": icon, label = "✅", f"{agent} Result"
    elif event == "ERROR": icon, label = "❌", f"{agent} Error"
    else: icon, label = "ℹ️", f"{agent} Info"

    with st.container(border=True):
        st.markdown(f"**{icon} {label}**")
        
        if animate:
            # 1. Fase Animazione (Typing)
            text_box = st.empty()
            
            # Formattiamo il testo per l'animazione
            stream_content = content
            if event == "ACTION":
                stream_content = f"```\n{content}\n```"
            elif event == "ERROR":
                stream_content = f"**ERROR:** {content}"
            
            stream_text(text_box, stream_content, speed=0.1) # VELOCITÀ SCRITTURA
            
            # 2. Fase Snap (Sostituzione col widget finale statico)
            text_box.empty()
            if event == "THOUGHT": st.info(content)
            elif event == "ACTION": st.code(content)
            elif event == "ERROR": st.error(content)
            else: st.write(content)
            
        else:
            # Rendering statico (per la cronologia)
            if event == "THOUGHT": st.info(content)
            elif event == "ACTION": st.code(content)
            elif event == "ERROR": st.error(content)
            else: st.write(content)
            
        st.caption(f"Time: {log_entry.get('timestamp', '')}")

# --- LOGICA DI ESECUZIONE (LIVE) ---
if run_btn:
    st.session_state.is_running = True
    st.session_state.logs = [] 
    if os.path.exists("agent_trace.jsonl"): os.remove("agent_trace.jsonl")
    
    initial_state = {"topic": topic, "syllabus": selected_paths, "retry_count": 0}
    seen_lines = 0
    
    try:
        # Loop Streaming LangGraph
        for event in app.stream(initial_state, config=config):
            if not event: continue
            
            # 1. Aggiorna Dashboard
            current_node = list(event.keys())[0]
            render_dashboard(current_node, mode="live")
            
            # 2. Leggi Nuovi Log da JSONL
            new_logs_batch = []
            if os.path.exists("agent_trace.jsonl"):
                with open("agent_trace.jsonl", "r") as f:
                    lines = f.readlines()
                    if len(lines) > seen_lines:
                        new_data = lines[seen_lines:]
                        for line in new_data:
                            try:
                                log_obj = json.loads(line)
                                new_logs_batch.append(log_obj)
                            except: pass
                        seen_lines = len(lines)
            
            # 3. RENDERIZZA IL FEED (LOGICA SEQUENZIALE STABILIZZATA)
            # Processiamo i nuovi log uno alla volta per evitare "salti" visivi
            for log_item in new_logs_batch:
                with feed_container.container():
                    st.caption("▼ Live Feed (Newest First) ▼")
                    
                    # A. Anima il log NUOVO in cima
                    render_log_card(log_item, animate=True)
                    
                    # B. Mostra subito sotto la storia VECCHIA (statica)
                    for old_log in reversed(st.session_state.logs):
                        render_log_card(old_log, animate=False)
                
                # Una volta finito di renderizzare/animare questo log, lo promuoviamo a "storia"
                st.session_state.logs.append(log_item)
            
            # 4. Check Fine
            if "publisher" in event and event["publisher"] and "final_file" in event["publisher"]["final_file"]:
                st.balloons()
                render_dashboard("PUBLISHER", mode="live")
                    
        st.session_state.is_running = False
        st.rerun()

    except Exception as e:
        st.error(f"Errore di Esecuzione: {e}")
        st.session_state.is_running = False

# --- PAUSE / HUMAN FEEDBACK ---
snapshot = app.get_state(config)
if snapshot.next:
    st.markdown("---")
    current_state = snapshot.values
    
    queries = []
    if "study_plan" in current_state:
        for section in current_state["study_plan"]:
            queries.extend(section.queries)
    else:
        queries = current_state.get("web_syllabus", [])

    with st.container(border=True):
        st.warning("🎯 **REVISIONE PIANO DI RICERCA** (Paused)")
        st.write("L'Agente attende approvazione per queste ricerche:")
        
        if queries:
            for i, q in enumerate(queries):
                st.markdown(f"{i+1}. `🔍 {q}`")
        else:
            st.write("Generating plan...")
            
        st.write("")
        col_fb, col_go = st.columns([3, 1])
        with col_fb:
            user_feedback = st.text_input("Istruzioni per l'Agente:", key="feedback_hitl")
        with col_go:
            st.write("") 
            if st.button("🚀 Conferma e Procedi", type="primary", use_container_width=True):
                app.update_state(config, {"feedback": user_feedback}, as_node="human")
                st.rerun()

# --- HISTORY & TIME TRAVEL ---
if not st.session_state.is_running and st.session_state.logs:
    with feed_container.container():
        st.caption("▼ Mission History (Complete) ▼")
        for log in reversed(st.session_state.logs):
            render_log_card(log, animate=False)
            
    st.markdown("---")
    st.subheader("🕰️ Time Machine Debugger")
    
    total_steps = len(st.session_state.logs)
    if total_steps > 0:
        step = st.slider("Rewind Step:", 0, total_steps - 1, total_steps - 1)
        
        log_at_step = st.session_state.logs[step]
        agent_at_step = log_at_step.get('agent', 'UNKNOWN')
        
        render_dashboard(agent_at_step, mode="replay")
        st.info(f"**Step {step + 1}**: {agent_at_step} -> {log_at_step.get('event')}")
        render_log_card(log_at_step, animate=False)
        
    files = glob.glob("generated_plans/*.docx")
    if files:
        latest_file = max(files, key=os.path.getctime)
        with open(latest_file, "rb") as f:
            st.download_button("📥 Scarica Documento Finale (DOCX)", f, file_name=os.path.basename(latest_file))