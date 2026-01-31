import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI

load_dotenv()

# Inizializziamo il modello Groq
# Usiamo Llama3-70b (per la gestione di istruzioni JSON complesse)
llm = ChatGroq(
    temperature=0, 
    model_name="llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY")
)

llm = ChatMistralAI(
    model="mistral-large-latest",  # Consigliato per logica complessa (Router/Planner)
    # model="open-mixtral-8x22b",  # Alternativa open source molto forte
    temperature=0
)