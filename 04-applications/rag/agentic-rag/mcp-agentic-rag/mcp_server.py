import os
from typing import List
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Updated import: Assumes FAQEngine and the FAQ text are in 'rag_app.py'
from rag_app import FAQEngine, PYTHON_FAQ_TEXT

# Load environment variables from .env file
load_dotenv()

# Configuration constants
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "python_faq_collection"  # Using a new collection for the Python data
HOST = "127.0.0.1"
PORT = 8080


# Create an MCP server instance
mcp_server = FastMCP("MCP-RAG-app",
                     host=HOST,
                     port=PORT)


@mcp_server.tool()
def python_faq_retrieval_tool(query: str) -> str:
    """    
    Retrieve the most relevant documents from the Python FAQ collection.     
    Use this tool when the user asks about general Python programming concepts.        
    
    Args:    
        query (str): The user query to retrieve the most relevant documents.            
        
        Returns:    
            str: The most relevant documents retrieved from the vector DB.    
    """    
    if not isinstance(query, str):     
        raise TypeError("Query must be a string.")        
    # Use the single, pre-initialized faq_engine instance for efficiency    
    return faq_engine.answer_question(query)



@mcp_server.tool()
def firecrawl_web_search_tool(query: str) -> List[str]:
    """    
    Search for information on a given topic using Firecrawl.    
    Use this tool when the user asks a specific question not related to the Python FAQ.    
    
    Args:    
        query (str): The user query to search for information.    
        
    Returns:    
        List[str]: A list of the most relevant web search results.    
    """    
    if not isinstance(query, str):     
        raise TypeError("Query must be a string.")    
        
    url = "https://api.firecrawl.dev/v1/search"    
    api_key = os.getenv('FIRECRAWL_API_KEY')    
    
    if not api_key:    
        return ["Error: FIRECRAWL_API_KEY environment variable is not set."]    
    payload = {"query": query, "timeout": 60000}    
    headers = {     
        "Authorization": f"Bearer {api_key}",        
        "Content-Type": "application/json"    
    }    
    
    try:    
        response = requests.post(url, json=payload, headers=headers)        
        response.raise_for_status() 
        # Raise an exception for bad status codes (4xx or 5xx)        
        # Assuming the API returns JSON with a key like "data" or "results"        # Adjust .get("data", ...) if the key is different        
        return response.json().get("data", ["No results found from web search."])    
    except requests.exceptions.RequestException as e:    
        return [f"Error connecting to Firecrawl API: {e}"]


# This should be at the end of the mcp_server.py file

if __name__ == "__main__":    
    # 1. Initialize our RAG Engine    
    print("Initializing FAQ Engine and setting up Qdrant collection...")    
    faq_engine = FAQEngine(qdrant_url=QDRANT_URL, collection_name=COLLECTION_NAME)        
    
    # 2. Ingest our data into the vector database    
    # This will create embeddings and store them    
    faq_engine.setup_collection(PYTHON_FAQ_TEXT)        
    
    # 3. Start the MCP server    
    print(f"Starting MCP server at http://{HOST}:{PORT}")    
    mcp_server.run()
