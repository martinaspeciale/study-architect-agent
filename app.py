import streamlit as st
import json
import os
import glob
from graph import app

st.set_page_config(page_title="Study Architect Feed", layout="wide", page_icon="🎓")

# --- CSS: Stile Dashboard, Log e Feed ---
st.markdown("""
<style>
    /* Stile Carte Dashboard */
    div[data-testid="stMetric"] {
        background-color: #1e1e1e;
        border: 1px solid #333;
        padding: 10px;
        border-radius: 8px;
    }
    /* LIVE MODE: Verde */
    .active-agent {
        border: 2px solid #00ff00 !important;
        background-color: #1b3a1b !important;
        box-shadow: 0 0 15px rgba(0, 255, 0, 0.4);
        color: #ffffff;
        transform: scale(1.05);
        font-weight: bold;
    }
    /* REPLAY MODE: Ambra */
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
    
    /* Stile Log */
    .streamlit-expanderHeader {
        font-family: monospace;
        font-size: 0.9em;
        font-weight: bold;
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
        
        # Se non attivo, stile spento
        if not is_active:
            style_class = "inactive-agent"
            icon = "⚪"
        
        placeholders[agent].markdown(f"""
        <div class="{style_class}" style="text-align: center; padding: 10px; border-radius: 8px; transition: all 0.2s;">
            <small>{agent}</small><br><span style="font-size:1.1em;">{icon}</span>
        </div>
        """, unsafe_allow_html=True)

# Inizializza Dashboard
if not st.session_state.is_running:
    render_dashboard("NONE")

# --- AREA LOG (Placeholder Dinamico) ---
st.markdown("---")
# Creiamo un contenitore VUOTO che sovrascriveremo ad ogni loop
# Questo è il segreto per far apparire i log "nuovi sopra" senza duplicati
feed_container = st.empty()

def render_log_card(log_entry, expanded=False):
    """Renderizza un singolo log verbose"""
    event = log_entry.get('event', 'INFO')
    agent = log_entry.get('agent', 'SYSTEM')
    content = log_entry.get('content', '')
    
    if event == "THOUGHT": icon, label = "🧠", f"**{agent}**"
    elif event == "ACTION": icon, label = "⚡", f"**{agent}** Azione"
    elif event == "Result" or event == "RESULT": icon, label = "✅", f"**{agent}** Risultato"
    elif event == "ERROR": icon, label = "❌", f"**{agent}** Errore"
    else: icon, label = "ℹ️", f"**{agent}** Info"

    with st.expander(f"{icon} {label}", expanded=expanded):
        if event == "THOUGHT": st.info(content)
        elif event == "ACTION": st.code(content)
        elif event == "ERROR": st.error(content)
        else: st.write(content)
        st.caption("Raw Data:")
        st.json(log_entry, expanded=False)

# --- LOGICA DI ESECUZIONE (LIVE) ---
if run_btn:
    st.session_state.is_running = True
    st.session_state.logs = [] # Reset
    if os.path.exists("agent_trace.jsonl"): os.remove("agent_trace.jsonl")
    
    initial_state = {"topic": topic, "syllabus": selected_paths, "retry_count": 0}
    seen_lines = 0
    
    try:
        # Loop Streaming
        for event in app.stream(initial_state, config=config):
            if not event: continue
            
            # 1. Aggiorna Dashboard (Chi sta lavorando?)
            current_node = list(event.keys())[0]
            render_dashboard(current_node, mode="live")
            
            # 2. Leggi Nuovi Log dal File
            if os.path.exists("agent_trace.jsonl"):
                with open("agent_trace.jsonl", "r") as f:
                    lines = f.readlines()
                    if len(lines) > seen_lines:
                        new_data = lines[seen_lines:]
                        for line in new_data:
                            try:
                                log_obj = json.loads(line)
                                st.session_state.logs.append(log_obj)
                            except: pass
                        seen_lines = len(lines)
            
            # 3. RENDERIZZA IL FEED INVERSO
            # Usiamo .container() dentro feed_container per pulire e riscrivere tutto
            with feed_container.container():
                st.caption("▼ Ultimi aggiornamenti (In tempo reale) ▼")
                
                # [TRUCCO] Iteriamo la lista al contrario: REVERSED
                # Il log più recente (l'ultimo della lista) viene disegnato per primo
                for log in reversed(st.session_state.logs):
                    # Espandiamo di default solo se è l'ultimo arrivato (il primo del loop)
                    is_latest = (log == st.session_state.logs[-1])
                    is_error = (log.get('event') == 'ERROR')
                    render_log_card(log, expanded=(is_latest or is_error))
            
            # 4. Controllo Finale
            if "publisher" in event and event["publisher"] and "final_file" in event["publisher"]["final_file"]:
                st.balloons()
                render_dashboard("PUBLISHER", mode="live")
                    
        st.session_state.is_running = False
        st.rerun()

    except Exception as e:
        st.error(f"Errore: {e}")
        st.session_state.is_running = False

# --- NUOVA SEZIONE: CONTROLLO PAUSA AGENTE ---
# Controlliamo se il grafo è fermo a un breakpoint
snapshot = app.get_state(config)

if snapshot.next: # Se l'agente è in pausa (es. su 'web_planner')
    st.markdown("---")

    # Recuperiamo il piano di ricerca dallo stato corrente
    current_state = snapshot.values
    queries = current_state.get("web_syllabus", [])

    with st.container(border=True):
        st.warning("🎯 **REVISIONE PIANO DI RICERCA**: L'agente ha pianificato queste query:")
        
        # Mostriamo il set di ricerche determinate (Slide 355)
        for i, q in enumerate(queries):
            st.markdown(f"{i+1}. `🔍 {q}`")
            
        st.write("")
        col_fb, col_go = st.columns([3, 1])
        
        with col_fb:
            user_feedback = st.text_input(
                "Istruzioni: (es. 'Togli la 2', 'Aggiungi ricerca su costi')", 
                key="feedback_hitl"
            )
        
        with col_go:
            st.write("") # Spacer
            if st.button("🚀 Conferma Piano", type="primary", use_container_width=True):
                # Se l'utente ha dato feedback, lo passiamo al nodo human
                # che si occuperà di ripulire o integrare le query.
                app.update_state(
                    config, 
                    {"feedback": user_feedback}, 
                    as_node="human_review"
                )
                
                # Riprendiamo l'esecuzione
                with feed_container.container():
                    for event in app.stream(None, config=config):
                        if event:
                            # Qui chiami la tua funzione di aggiornamento feed/dashboard
                            pass
                st.rerun()




# --- TIME TRAVEL (Post-Esecuzione) ---
if not st.session_state.is_running and st.session_state.logs:
    
    # Renderizziamo l'ultimo stato del feed (per non lasciare lo schermo vuoto)
    with feed_container.container():
        st.caption("▼ Storia Completa (Inversa) ▼")
        for log in reversed(st.session_state.logs):
            render_log_card(log, expanded=False)

    # UI Time Travel in basso
    st.markdown("---")
    st.subheader("🕰️ Time Machine")
    
    total_steps = len(st.session_state.logs)
    if total_steps > 0:
        step = st.slider("Scorri indietro nel tempo:", 0, total_steps - 1, total_steps - 1)
        
        # Recupera il momento passato
        log_at_step = st.session_state.logs[step]
        agent_at_step = log_at_step.get('agent', 'UNKNOWN')
        
        # Aggiorna Dashboard (Colore Ambra)
        render_dashboard(agent_at_step, mode="replay")
        
        # Mostra dettaglio isolato
        st.info(f"**Step {step + 1}**: L'agente {agent_at_step} stava eseguendo: {log_at_step.get('event')}")
        render_log_card(log_at_step, expanded=True)
        
    # Download File Finale
    files = glob.glob("generated_plans/*.docx")
    if files:
        latest_file = max(files, key=os.path.getctime)
        with open(latest_file, "rb") as f:
            st.download_button("📥 Scarica Documento Finale", f, file_name=os.path.basename(latest_file))