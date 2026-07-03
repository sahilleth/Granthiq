from typing import List, Dict, Any
from langchain_core.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)


RAG_SYSTEM_PROMPT = """You are a helpful AI assistant with access to a knowledge base.

Your role:
- Answer questions based on the provided context
- If the answer isn't in the context, say "I don't have enough information to answer that"
- Cite specific parts of the context when making claims
- Be clear, concise, and accurate

Remember: Always base your answers on the provided context."""

CONVERSATIONAL_SYSTEM_PROMPT = """You are a friendly and knowledgeable AI assistant.

Your personality:
- Helpful and patient
- Clear and concise
- Honest about limitations
- Encouraging and supportive

Your goal is to help users understand information from their documents."""

TECHNICAL_SYSTEM_PROMPT = """You are an expert technical AI assistant specialized in analyzing documentation and technical materials.

Your approach:
- Precise and technically accurate
- Use domain-specific terminology appropriately  
- Provide detailed explanations when needed
- Reference specific sections
- Explain complex concepts clearly"""


RAG_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    ("human", """Context:
{context}

Question: {question}

Please answer based only on the context above.""")
])

RAG_WITH_HISTORY_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", """Context:
{context}

Question: {question}

Answer based on the context and conversation history.""")
])

SUMMARIZATION_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "You are an expert at summarizing content clearly and concisely."),
    ("human", """Please summarize the following text.

Text:
{text}

Provide a {length} summary focusing on:
- Main ideas and key points
- Important details
- Key conclusions

Summary:""")
])

QUESTION_ANSWERING_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that answers questions accurately."),
    ("human", "{question}")
])



def build_context(chunks: List[Dict[str, Any]], max_chunks: int = 5) -> str:
    """
    Build context string from document chunks.
    
    Args:
        chunks: List of document chunks
        max_chunks: Maximum number of chunks to include
    
    Returns:
        Formatted context string
    """
    parts = []
    for i, chunk in enumerate(chunks[:max_chunks], 1):
        text = chunk.get('text', chunk.get('content', ''))
        
      
        if 'metadata' in chunk:
            meta = chunk['metadata']
            source = meta.get('source', meta.get('file_name', ''))
            page = meta.get('page_number', '')
            
            if source and page:
                header = f"[Source {i}: {source}, Page {page}]"
            elif source:
                header = f"[Source {i}: {source}]"
            else:
                header = f"[{i}]"
            
            parts.append(f"{header}\n{text}")
        else:
            parts.append(f"[{i}] {text}")
    
    return "\n\n".join(parts)


def build_rag_prompt(context: str, question: str) -> str:
    """
    Build a simple RAG prompt.
    
    Args:
        context: Context string
        question: User question
    
    Returns:
        Formatted prompt
    """
    return f"""Context:
{context}

Question: {question}

Answer based only on the context above:"""


def format_chat_history(messages: List[Dict[str, str]]) -> str:
    """
    Format chat history for display.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
    
    Returns:
        Formatted history string
    """
    parts = []
    for msg in messages:
        role = msg.get('role', '').capitalize()
        content = msg.get('content', '')
        parts.append(f"{role}: {content}")
    
    return "\n".join(parts)



__all__ = [
    
    "RAG_SYSTEM_PROMPT",
    "CONVERSATIONAL_SYSTEM_PROMPT",
    "TECHNICAL_SYSTEM_PROMPT",
    
   
    "RAG_PROMPT_TEMPLATE",
    "RAG_WITH_HISTORY_TEMPLATE",
    "SUMMARIZATION_TEMPLATE",
    "QUESTION_ANSWERING_TEMPLATE",
    
  
    "build_context",
    "build_rag_prompt",
    "format_chat_history",
]
