import json
import datetime
import os
from termcolor import colored

# Ensure logs directory exists
LOG_FILE = "agent_trace.jsonl"

class AgentLogger:
    def __init__(self):
        # Clear old logs on restart 
        with open(LOG_FILE, "w") as f:
            f.write("")

    def log_event(self, agent_name, event_type, content, metadata=None):
        """
        Logs an event to JSONL and prints to console.
        Structure: {"timestamp": ..., "agent": ..., "event": ..., "data": ...}
        """
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "agent": agent_name,
            "event": event_type,
            "content": content,
            "metadata": metadata or {}
        }
        
        # Write to JSONL (The Machine Readable Log)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
            
        # Print to Console (The Human Readable Output)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        if event_type == "START":
            print(colored(f"\n[{timestamp}] --- {agent_name} ---", "green", attrs=["bold"]))
        elif event_type == "THOUGHT":
            print(colored(f"   [Thinking] {content}", "cyan"))
        elif event_type == "ACTION":
            print(colored(f"   [Action] {content}", "yellow"))
        elif event_type == "ERROR":
            print(colored(f"   [Error] {content}", "red"))
        elif event_type == "RESULT":
            print(colored(f"   [Result] {content}", "blue"))
        else:
            print(f"   [{event_type}] {content}")

# Singleton instance
logger = AgentLogger()