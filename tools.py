import os
from langchain_core.tools import tool
from tavily import TavilyClient
from logger import logger

@tool
def search_educational_resources(query: str):
    """
    Performs an advanced web search for educational content, tutorials, and documentation.
    Returns a list of results with titles, URLs, and raw content.
    """
    try:
        # [Theory] Robust Tools (Slide 8): Check inputs and handle errors gracefully
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return "Error: TAVILY_API_KEY not found in environment."

        client = TavilyClient(api_key=api_key)
        
        # We enforce "advanced" depth as per original logic
        response = client.search(
            query=query, 
            search_depth="advanced", 
            max_results=5
        )
        
        # [Theory] Observability (Slide 19): Log the atomic tool event
        logger.log_event("TOOL", "ACTION", f"Executed search for: '{query}'")
        
        return response.get("results", [])

    except Exception as e:
        # [Theory] Resilience (Slide 17): Return error string, don't crash
        error_msg = f"Error executing search: {str(e)}"
        logger.log_event("TOOL", "ERROR", error_msg)
        return error_msg