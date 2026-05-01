"""
Utility functions for context engineering notebooks.
"""

from rich.console import Console
from rich.panel import Panel
import json

console = Console()


def format_message_content(message):
    """Convert message content to displayable string"""
    if isinstance(message.content, str):
        return message.content
    elif isinstance(message.content, list):
        # Handle complex content like tool calls
        parts = []
        for item in message.content:
            if item.get('type') == 'text':
                parts.append(item['text'])
            elif item.get('type') == 'tool_use':
                parts.append(f"\n🔧 Tool Call: {item['name']}")
                parts.append(f"   Args: {json.dumps(item['input'], indent=2)}")
        return "\n".join(parts)
    else:
        return str(message.content)


def format_messages(messages):
    """Format and display a list of messages with Rich formatting"""
    for m in messages:
        msg_type = m.__class__.__name__.replace('Message', '')
        content = format_message_content(m)

        if msg_type == 'Human':
            console.print(Panel(content, title="🧑 Human", border_style="blue"))
        elif msg_type == 'Ai':
            console.print(Panel(content, title="🤖 Assistant", border_style="green"))
        elif msg_type == 'Tool':
            console.print(Panel(content, title="🔧 Tool Output", border_style="yellow"))
        else:
            console.print(Panel(content, title=f"📝 {msg_type}", border_style="white"))


def format_message(messages):
    """Alias for format_messages for backward compatibility"""
    return format_messages(messages)


def format_retriever_results(result, title="Retriever Tool Results"):
    """Format and display retriever tool results with proper text wrapping
    
    Args:
        result: List of documents from retriever tool or a string
        title: Title to display above the results
    """
    # Initialize console for rich formatting with width limit
    formatted_console = Console(width=100)
    
    formatted_console.print(f"[bold green]{title}:[/bold green]")
    
    # Handle case where result is a string
    if isinstance(result, str):
        formatted_console.print(f"\n[yellow]Content:[/yellow]")
        formatted_console.print(result, style="white")
        return
    
    # Handle case where result is a list of documents
    for i, doc in enumerate(result):
        formatted_console.print(f"\n[bold blue]Document {i+1}:[/bold blue]")
        
        # Check if doc has metadata attribute (Document object)
        if hasattr(doc, 'metadata'):
            formatted_console.print(f"[cyan]Source:[/cyan] {doc.metadata.get('source', 'Unknown')}")
            formatted_console.print(f"[yellow]Content:[/yellow]")
            formatted_console.print(doc.page_content, style="white")
        else:
            # Handle case where doc is just a string
            formatted_console.print(f"[yellow]Content:[/yellow]")
            formatted_console.print(str(doc), style="white")