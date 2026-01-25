# Multi-Agent Study Architect

* **Course:** Symbolic and Evolutionary Artificial Intelligence (SEAI)
* **Program:** Master in Artificial Intelligence and Data Engineering (AIDE)
* **Institution:** University of Pisa

This project leverages **LangGraph** to build an Agentic AI system that creates structured study plans and sources real-world educational materials. It implements advanced orchestration patterns including Human-in-the-Loop validation and Tool Use.

## Project Overview

The goal of this tool is to separate reasoning (planning) from action (research) to prevent common LLM pitfalls like hallucination. By treating the study plan as a dynamic state object, the system allows for iterative refinement and human oversight.

### Key Features
* **Hybrid Knowledge Engine:** Automatically scans a local `knowledge_base` folder for PDF/DOCX files and intelligently merges them with live Web Research.
* **"Thinking" Agents:** All agents (Judge, Planner, Finder) output internal monologues, showing their reasoning, confidence scores, and gap analysis in real-time.
* **Human-in-the-Loop:** Pauses execution to allow the user to review local findings and critique the search plan before the agent goes online.
* **Automated Publishing:** Compiles everything (summaries, links, local insights) into a professionally formatted `.docx` study guide stored in `generated_plans`.
* **Smart Deduplication:** The Web Finder ensures source variety by tracking and filtering duplicate URLs across different search queries.
* **Model:** Powered by **Llama-3 via Groq** for low-latency reasoning.


## Architecture

The system uses a linear **Hybrid State Graph** with 7 specialized nodes:

1.  **Init Node:** Captures the user's topic and scans the `knowledge_base` folder for relevant local documents.
2.  **Local Miner Node:** Ingests selected files (PDF/DOCX), extracting and summarizing key concepts relevant to the topic.
3.  **Judge Node:** acts as a quality gatekeeper, scoring the relevance of local files (0-100) and providing a critique before the human sees them.
4.  **Human Review Node:** Presents the Local findings and Judge's critique to the user, asking for approval or specific focus for the web search.
5.  **Web Planner Node:** Performs a "Gap Analysis" by comparing local knowledge against the topic to generate 3 targeted search queries for missing information.
6.  **Web Finder Node:** Executes the search plan using Tavily, filtering duplicates and summarizing distinct educational sources.
7.  **Publisher Node:** Aggregates local and web resources into a final Word document, flagging irrelevant content in red.

## Setup and Installation

### 1. Prerequisites
* Python 3.10+
* A Groq API Key
* A Tavily API Key

### 2. Installation

Initialize the virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration
1. Create a `.env` file in the root directory and add your API keys:
```plaintext
GROQ_API_KEY=your_groq_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```
2. Create a folder named `knowledge_base` in the root directory. Drop any PDFs or DOCX notes you want the agent to use in here.

## Usage
Run the main orchestration script:
```bash
python graph.py
```

1. **Topic & Files**: Enter your topic. The agent will list files found in `knowledge_base/` — select which ones to use (e.g., "1, 2" or "all").
2. **Validation**: The Judge will score your files. If they are irrelevant, it will warn you.
3. **Human Review**: You will see the local summaries. Press ENTER to approve the Web Search Plan or type instructions to guide it.
4. **Gap Analysis & Search**: The Planner identifies missing concepts, and the Finder hunts for them on the web.
5. **Final Output**: A new study guide is saved in the `generated_plans/` folder.