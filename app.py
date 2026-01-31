import streamlit as st
import os
import time
import glob
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

# Import dai tuoi file locali
from state import AgentState
from nodes import (
    init_node, local_miner_node, judge_node, human_review_node, 
    topic_router_node, web_planner_node, web_finder_node, 
    search_critic_node, publisher_node
)

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Agentic Chat", page_icon="🧠")

# --- CSS: STILE PULITO E LOGS ---
st.markdown("""
<style>
    header, footer {visibility: hidden;}
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    
    .stChatInput {
        position: fixed; 
        bottom: 20px; 
        z-index: 1000; 
        width: 58%; 
    }

    .thought-box {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px 15px;
        margin-bottom: 10px;
        font-family: 'Courier New', monospace; 
        font-size: 0.85rem;
        line-height: 1.4;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        color: #333;
    }
    
    .thought-header {
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #f0f0f0;
        padding-bottom: 4px;
        font-size: 0.75rem;
    }
    
    .header-blue { color: #2563eb; border-left: 4px solid #2563eb; }
    .header-green { color: #059669; border-left: 4px solid #059669; }
    .header-purple { color: #7c3aed; border-left: 4px solid #7c3aed; }
    .header-orange { color: #d97706; border-left: 4px solid #d97706; }
    .header-red { color: #dc2626; border-left: 4px solid #dc2626; }
</style>
""", unsafe_allow_html=True)

# --- INIZIALIZZAZIONE STATO ---
if "messages" not in st.session_state: st.session_state.messages = [] 
if "logs" not in st.session_state: st.session_state.logs = [] 
if "thread_id" not in st.session_state: st.session_state.thread_id = "sess_v1"
if "graph_state" not in st.session_state: st.session_state.graph_state = None

# --- LOGICA GRAFO ---
def check_verdict(state: AgentState):
    # Logica di uscita dal loop finder-critic
    if state.get("is_approved") or state.get("retry_count", 0) >= 2:
        return "proceed"
    return "loop"

@st.cache_resource
def get_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("init", init_node)
    workflow.add_node("local_miner", local_miner_node)
    workflow.add_node("judge", judge_node)
    workflow.add_node("human", human_review_node)
    workflow.add_node("router", topic_router_node)
    workflow.add_node("web_planner", web_planner_node)
    workflow.add_node("web_finder", web_finder_node)
    workflow.add_node("search_critic", search_critic_node) 
    workflow.add_node("publisher", publisher_node)

    workflow.set_entry_point("init")
    workflow.add_edge("init", "local_miner")
    workflow.add_edge("local_miner", "judge")
    workflow.add_edge("judge", "human")
    workflow.add_edge("human", "router")       
    workflow.add_edge("router", "web_planner") 
    workflow.add_edge("web_planner", "web_finder")
    workflow.add_edge("web_finder", "search_critic")
    workflow.add_conditional_edges("search_critic", check_verdict, {"proceed": "publisher", "loop": "web_finder"})
    workflow.add_edge("publisher", END)

    return workflow.compile(checkpointer=MemorySaver(), interrupt_before=["human"])

app_graph = get_graph()
config = {"configurable": {"thread_id": st.session_state.thread_id}}

# --- FUNZIONE VISUALE: REVERSE LOGGING CON TYPING EFFECT ---
def stream_log_reverse(placeholder, agent_name, verbose_text, color_class="header-blue"):
    def make_html(content, final=False):
        cursor = "█" if not final else ""
        return f"""<div class='thought-box {color_class}'>
<div class='thought-header'>
<span>⚡ {agent_name}</span>
<span>{'COMPLETATO' if final else 'IN CORSO...'}</span>
</div>
<div style='white-space: pre-wrap;'>{content}{cursor}</div>
</div>"""
    
    old_logs_html = "".join(st.session_state.logs)
    
    # Typing effect: procediamo a blocchi di caratteri per fluidità
    step = 4
    for i in range(0, len(verbose_text) + step, step):
        current_text = verbose_text[:i]
        temp_html = make_html(current_text, final=False) + old_logs_html
        placeholder.markdown(temp_html, unsafe_allow_html=True)
        time.sleep(0.01)
        
    final_block_html = make_html(verbose_text, final=True)
    st.session_state.logs.insert(0, final_block_html)
    placeholder.markdown("".join(st.session_state.logs), unsafe_allow_html=True)

# --- ESECUZIONE AGENTE ---
def run_agent(log_placeholder, user_input=None, resume=False):
    inputs = None
    if resume and user_input:
        # Ripresa dopo pausa umana
        app_graph.update_state(config, {"feedback": user_input})
        stream_log_reverse(log_placeholder, "USER INPUT", f"Ricevuto feedback:\n> {user_input}", "header-green")
    elif not resume:
        # Nuova sessione
        inputs = {"topic": user_input, "syllabus": [], "feedback": None, "retry_count": 0}
        stream_log_reverse(log_placeholder, "SYSTEM", f"Avvio sessione per: '{user_input}'.", "header-purple")

    try:
        # Stream con updates per ricevere dati ad ogni nodo
        for event in app_graph.stream(inputs if not resume else None, config=config, stream_mode="updates"):
            if not isinstance(event, dict): continue

            for node, data in event.items():
                if data is None: continue
                
                # Se data è una tupla (comune in certi checkpoint), prendi il primo elemento
                if isinstance(data, tuple):
                    data = data[0] if len(data) > 0 else {}

                # RECUPERO PENSIERI DAL NODO
                txt = data.get("current_node_logs", f"Agente {node} ha completato il lavoro.")
                
                node_style = {
                    "init": "header-purple", "local_miner": "header-orange",
                    "judge": "header-green", "human": "header-red",
                    "router": "header-purple", "web_planner": "header-blue",
                    "web_finder": "header-blue", "search_critic": "header-orange",
                    "publisher": "header-green", "__interrupt__": "header-red"
                }
                color = node_style.get(node, "header-blue")
                
                stream_log_reverse(log_placeholder, node.upper(), txt, color)

                if node == "publisher":
                    f = data.get("final_file")
                    if f:
                        st.session_state.messages.append(AIMessage(content=f"✅ **Fatto!** Documento generato: `{os.path.basename(f)}`"))

    except Exception as e:
        stream_log_reverse(log_placeholder, "DEBUG ERROR", f"Errore rilevato: {str(e)}", "header-red")
        st.error(f"Errore nel grafo: {e}")

    # Controllo se il grafo è in pausa
    snapshot = app_graph.get_state(config)
    if snapshot.next and "human" in snapshot.next:
        st.session_state.graph_state = "WAITING"
        fb = snapshot.values.get('feedback', 'Richiesto intervento umano.')
        stream_log_reverse(log_placeholder, "BREAKPOINT", f"In attesa di istruzioni.\nMessaggio: {fb}", "header-red")
        st.session_state.messages.append(AIMessage(content=f"⚠️ **Pausa.** {fb}\nScrivi qualcosa per procedere."))
    else:
        st.session_state.graph_state = "DONE"

# --- LAYOUT UI ---
with st.sidebar:
    st.header("📂 Knowledge Base")
    files = st.file_uploader("Carica file (PDF/TXT)", accept_multiple_files=True)
    if files:
        if not os.path.exists("knowledge_base"): os.makedirs("knowledge_base")
        for f in files:
            with open(f"knowledge_base/{f.name}", "wb") as w: w.write(f.getbuffer())
        st.success(f"{len(files)} file pronti.")
    
    st.divider()
    if st.button("🗑️ Reset Chat"):
        st.session_state.clear()
        st.rerun()

chat_col, log_col = st.columns([6, 4])

with log_col:
    st.subheader("🧠 Thought Flow")
    log_container = st.container(height=700, border=True)
    with log_container:
        main_log_placeholder = st.empty()
        if st.session_state.logs:
            main_log_placeholder.markdown("".join(st.session_state.logs), unsafe_allow_html=True)

with chat_col:
    st.subheader("💬 Study Architect")
    chat_box = st.container(height=600)
    with chat_box:
        for m in st.session_state.messages:
            role = "user" if isinstance(m, HumanMessage) else "assistant"
            with st.chat_message(role): st.write(m.content)

    prompt = st.chat_input("Di cosa vuoi parlare?")
    
    if prompt:
        st.session_state.messages.append(HumanMessage(content=prompt))
        with chat_box:
            with st.chat_message("user"): st.write(prompt)
        
        is_resume = (st.session_state.graph_state == "WAITING")
        run_agent(main_log_placeholder, user_input=prompt, resume=is_resume)
        st.rerun()