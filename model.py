import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# Inizializziamo il modello Groq
# Usiamo Llama3-70b (per la gestione di istruzioni JSON complesse)
llm = ChatGroq(
    temperature=0, 
    model_name="llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY")
)