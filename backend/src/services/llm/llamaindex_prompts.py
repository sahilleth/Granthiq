from llama_index.core import PromptTemplate


DEFAULT_TEXT_QA_TEMPLATE = PromptTemplate(
    """Context information is below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the question.

**Response Guidelines:**
1. **FORMATTING**: You MUST use double newlines (`\n\n`) between every paragraph. Do NOT output a single block of text.
2. **CITATIONS**: You MUST use **BOLD** numbered citations exactly like this: **[1]** at the end of sentences used.
3. **CONTENT**: DIRECTLY and CONCISELY answer the question.

Question: {query_str}
Answer: """
)

DEFAULT_REFINE_TEMPLATE = PromptTemplate(
    """The original question is as follows: {query_str}

We have provided an existing answer: {existing_answer}

We have the opportunity to refine the existing answer with some more context below.
---------------------
{context_msg}
---------------------

Refine the original answer to better answer the question.

**Guidelines:**
1. **FORMATTING**: You MUST use double newlines (`\n\n`) between paragraphs.
2. **CITATIONS**: Add new inline citations as **[X]** (bold) where appropriate.

If the context isn't useful, return the original answer.

Refined Answer: """
)

DEFAULT_TREE_SUMMARIZE_TEMPLATE = PromptTemplate(
    """Context information from multiple sources is below.
---------------------
{context_str}
---------------------
Given the information from multiple sources, answer the question.

**Response Guidelines:**

1. **FORMATTING IS CRITICAL**:
   - You MUST use double newlines (`\n\n`) between every paragraph.
   - You MUST use double newlines (`\n\n`) before every Header.
   - Ensure the text is readable and not a single block.

2. **CITE SOURCES INLINE**:
   - You MUST use **BOLD** numbered citations exactly like this: **[1]**, **[2]** at the end of every sentence that uses information.

3. **CONTENT**:
   - DIRECTLY and CONCISELY answer the question.
   - Synthesize information from multiple sources.

Question: {query_str}
Answer: """
)


CITATION_TEXT_QA_TEMPLATE = PromptTemplate(
    """Context information is below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the question DIRECTLY and CONCISELY.
When referencing information from the context, cite the source using [Source X] format where X corresponds to the source number.

Important guidelines:
- Answer ONLY what is asked in the question - stay focused
- Be precise and concise - avoid unnecessary details
- Base your answer SOLELY on the provided context
- Do NOT include information not directly relevant to the question
- If the exact answer isn't explicitly stated but can be inferred from the context, please do so and state "Based on the context...".
- Only say "I don't have enough information" if the context provides NO relevant information.
- Cite sources when making specific claims or quoting information

Question: {query_str}
Answer: """
)

CITATION_REFINE_TEMPLATE = PromptTemplate(
    """The original question is as follows: {query_str}

We have provided an existing answer: {existing_answer}

We have the opportunity to refine the existing answer
(only if needed) with some more context below.
---------------------
{context_msg}
---------------------
Given the new context, refine the original answer to better answer the question.
When referencing new information, cite the source using [Source X] format.
If the context isn't useful, return the original answer.

Refined Answer: """
)


TECHNICAL_TEXT_QA_TEMPLATE = PromptTemplate(
    """You are an expert technical assistant. Context information is below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, provide a precise technical answer.
Use domain-specific terminology appropriately and explain complex concepts clearly.

Guidelines:
- Be technically accurate and precise
- Use appropriate technical terminology
- Provide detailed explanations when needed
- Reference specific sections or concepts from the context
- If information is not in the context, state that clearly

Question: {query_str}
Answer: """
)

TECHNICAL_REFINE_TEMPLATE = PromptTemplate(
    """The original technical question is: {query_str}

Existing answer: {existing_answer}

Additional context:
---------------------
{context_msg}
---------------------
Refine the existing answer with the new technical context if it adds value.
Maintain technical accuracy and use appropriate terminology.
If the new context doesn't improve the answer, return the original.

Refined Answer: """
)


CONVERSATIONAL_TEXT_QA_TEMPLATE = PromptTemplate(
    """You are a helpful and friendly AI assistant. Context information is below.
---------------------
{context_str}
---------------------
Given the context information, provide a clear and helpful answer in a conversational tone.

**Guidelines:**
1. **FORMATTING IS CRITICAL**:
   - You MUST use double newlines (`\n\n`) between every paragraph.
   - You MUST use double newlines (`\n\n`) before every Header.
   - Use **H3 Headers (###)** and **Bold** text for clarity.

2. **CITE SOURCES INLINE**:
   - Even in conversation, you MUST use **BOLD** numbered citations exactly like this: **[1]**, **[2]** at the end of every sentence that uses information.
   - Quote specific phrases: "text" **[1]**.

3. **TONE**:
   - Be friendly, patient, and encouraging.
   - Explain things clearly and concisely.

Question: {query_str}

Answer (Conversational but Formatted with Double Newlines and **[1]** Citations): """
)

CONVERSATIONAL_REFINE_TEMPLATE = PromptTemplate(
    """The original question is: {query_str}

We have an existing answer: {existing_answer}

Here's some additional context:
---------------------
{context_msg}
---------------------

Refine the answer in a friendly, conversational way if the new context helps.

**GUIDELINES:**
1. **MAINTAIN FORMATTING**: You MUST use double newlines (`\n\n`) between paragraphs. Key points should be Bold.
2. **INTEGRATE CITATIONS**: Add new inline citations exactly as **[X]** (bold) where appropriate.
3. **TONE**: Keep it friendly and clear.

If the new source adds no value, return the original answer.

Refined Answer (with Double Newlines and **[1]** Citations): """
)

    
COMPREHENSIVE_TEXT_QA_TEMPLATE = PromptTemplate(
    """Context information is below.
---------------------
{context_str}
---------------------
Given the context information, provide a comprehensive and detailed answer.

Guidelines:
- Provide a thorough answer covering all relevant aspects
- Include important details and nuances
- Structure your answer clearly (use bullet points or sections if helpful)
- Cite specific information from the context
- If information is missing, acknowledge what you can and cannot answer

Question: {query_str}
Answer: """
)

COMPREHENSIVE_REFINE_TEMPLATE = PromptTemplate(
    """The original question is: {query_str}

Existing comprehensive answer: {existing_answer}

Additional context to consider:
---------------------
{context_msg}
---------------------
Enhance the comprehensive answer with the new context if it adds important details or corrections.
Maintain the comprehensive nature of the answer.
If the new context doesn't add value, return the original answer.

Refined Answer: """
)


# =============================================================================
# NOTEBOOKLM-STYLE PROMPTS - Detailed responses with inline citations
# =============================================================================

NOTEBOOKLM_TEXT_QA_TEMPLATE = PromptTemplate(
    """You are an intelligent research assistant helping users understand their documents.
    
    Context information from the user's sources is below. Each source is clearly numbered (e.g., source 1, source 2).
    ---------------------
    {context_str}
    ---------------------
    
    Based ONLY on the provided sources, answer the user's question with a DETAILED and COMPREHENSIVE response.
    
    **CRITICAL FORMATTING RULES (MUST FOLLOW):**
    
    1. **PARAGRAPHS = DOUBLE NEWLINES**: You MUST use TWO newlines (`\n\n`) between every single paragraph. A single newline is FORBIDDEN.
    2. **HEADERS = DOUBLE NEWLINES**: You MUST use TWO newlines (`\n\n`) before and after every Header.
    3. **CITATIONS = BOLD**: You MUST use **[1]** format (Bold brackets) corresponding to the SOURCE NUMBER in the context.
       - DO NOT cite page numbers (e.g., [56]).
       - DO NOT use [0]. Start with [1].
       - ONLY use the source numbers provided in the context list above.
    
    **Content Guidelines:**
    - Use **H3 Headers (###)** for main topics.
    - Use **Bullet Points** for lists.
    - Quote specific phrases: "text" **[1]**.
    - Ignore metadata fields like 'user_id', 'file_path'.
    
    Question: {query_str}
    
    Answer (Start with a H3 Header or Intro, use \n\n for spacing): """
)

NOTEBOOKLM_REFINE_TEMPLATE = PromptTemplate(
    """The original question is: {query_str}
    
    We have an existing answer: {existing_answer}
    
    Additional source material:
    ---------------------
    {context_msg}
    ---------------------
    
    TASK: Enhance the existing answer with new information.
    
    **CRITICAL FORMATTING RULES (MUST FOLLOW):**
    1. **PARAGRAPHS = DOUBLE NEWLINES**: You MUST use TWO newlines (`\n\n`) between paragraphs.
    2. **CITATIONS = BOLD**: Add new inline citations exactly as **[X]** (bold) using the SOURCE NUMBER from the context. (e.g. [1]).
       - DO NOT cite using page numbers.
    3. **HEADERS**: Ensure Headers have `\n\n` before and after.
    
    If the new source adds no value, return the original answer.
    
    Enhanced Answer (maintain \n\n spacing): """
)


def get_prompt_templates(
    prompt_style: str = "default",
    include_citations: bool = True,
) -> dict:
    """
    Get prompt templates based on style preference.
    
    Args:
        prompt_style: Style of prompts ('default', 'notebooklm', 'citation', 'technical', 'conversational', 'comprehensive')
        include_citations: Whether to include citation instructions (for citation style)
        
    Returns:
        Dictionary with 'text_qa_template' and 'refine_template' keys
    """
    # NotebookLM style is now the default for citation-enabled prompts
    # It provides detailed, structured responses with inline citations
    if prompt_style == "notebooklm" or (prompt_style == "default" and include_citations):
        return {
            "text_qa_template": NOTEBOOKLM_TEXT_QA_TEMPLATE,
            "refine_template": NOTEBOOKLM_REFINE_TEMPLATE,
        }
    elif prompt_style == "citation":
        # Original citation style (more concise)
        return {
            "text_qa_template": CITATION_TEXT_QA_TEMPLATE,
            "refine_template": CITATION_REFINE_TEMPLATE,
        }
    elif prompt_style == "technical":
        return {
            "text_qa_template": TECHNICAL_TEXT_QA_TEMPLATE,
            "refine_template": TECHNICAL_REFINE_TEMPLATE,
        }
    elif prompt_style == "conversational":
        return {
            "text_qa_template": CONVERSATIONAL_TEXT_QA_TEMPLATE,
            "refine_template": CONVERSATIONAL_REFINE_TEMPLATE,
        }
    elif prompt_style == "comprehensive":
        return {
            "text_qa_template": COMPREHENSIVE_TEXT_QA_TEMPLATE,
            "refine_template": COMPREHENSIVE_REFINE_TEMPLATE,
        }
    else:  # explicit default without citations
        return {
            "text_qa_template": DEFAULT_TEXT_QA_TEMPLATE,
            "refine_template": DEFAULT_REFINE_TEMPLATE,
        }


def get_tree_summarize_template(
    prompt_style: str = "default",
) -> PromptTemplate:
    """
    Get tree summarize template based on style.
    
    Args:
        prompt_style: Style of prompt ('default', 'notebooklm', 'technical', 'conversational', 'comprehensive')
        
    Returns:
        PromptTemplate for tree summarization
    """
    if prompt_style == "notebooklm":
        return PromptTemplate(
            """You are an intelligent research assistant helping users understand their documents.

Context information from the user's sources is below. Each source is numbered.
---------------------
{context_str}
---------------------

Based on the provided sources, answer the user's question with a DETAILED and COMPREHENSIVE response.

**CRITICAL FORMATTING RULES (MUST FOLLOW):**

1. **PARAGRAPHS = DOUBLE NEWLINES**: You MUST use TWO newlines (`\n\n`) between every single paragraph. A single newline is FORBIDDEN.
2. **HEADERS = DOUBLE NEWLINES**: You MUST use TWO newlines (`\n\n`) before and after every Header.
3. **CITATIONS = BOLD**: You MUST use **[1]** format (Bold brackets) for citations.

**Content Guidelines:**
- Use **H3 Headers (###)** for main topics.
- Use **Bullet Points** for lists.
- Quote specific phrases: "text" **[1]**.

Question: {query_str}

Answer (Start with a H3 Header or Intro, use \n\n for spacing): """
        )
    elif prompt_style == "technical":
        return PromptTemplate(
            """You are an expert technical assistant. Context information from multiple sources is below.
---------------------
{context_str}
---------------------
Given the information from multiple sources, provide a precise technical answer.
Use domain-specific terminology appropriately.

Question: {query_str}
Answer: """
        )
    elif prompt_style == "conversational":
        return PromptTemplate(
            """You are a helpful assistant. Context information from multiple sources is below.
---------------------
{context_str}
---------------------
Given the information from multiple sources, provide a clear and friendly answer.

**Response Guidelines:**

1. **FORMATTING IS CRITICAL**:
   - You MUST use double newlines (`\n\n`) between every paragraph.
   - You MUST use double newlines (`\n\n`) before every Header.
   - Use **Bold** text for key points.

2. **CITE SOURCES INLINE**:
   - Even in conversation, you MUST use **BOLD** numbered citations exactly like this: **[1]**, **[2]** at the end of every sentence that uses information.

3. **TONE**:
   - Be friendly but clear.

Question: {query_str}

Answer: """
        )
    elif prompt_style == "comprehensive":
        return PromptTemplate(
            """Context information from multiple sources is below.
---------------------
{context_str}
---------------------
Given the information from multiple sources, provide a comprehensive and detailed answer covering all relevant aspects.

Question: {query_str}
Answer: """
        )
    else:  # default
        return DEFAULT_TREE_SUMMARIZE_TEMPLATE


__all__ = [
    "DEFAULT_TEXT_QA_TEMPLATE",
    "DEFAULT_REFINE_TEMPLATE",
    "DEFAULT_TREE_SUMMARIZE_TEMPLATE",
    "CITATION_TEXT_QA_TEMPLATE",
    "CITATION_REFINE_TEMPLATE",
    "NOTEBOOKLM_TEXT_QA_TEMPLATE",
    "NOTEBOOKLM_REFINE_TEMPLATE",
    "TECHNICAL_TEXT_QA_TEMPLATE",
    "TECHNICAL_REFINE_TEMPLATE",
    "CONVERSATIONAL_TEXT_QA_TEMPLATE",
    "CONVERSATIONAL_REFINE_TEMPLATE",
    "COMPREHENSIVE_TEXT_QA_TEMPLATE",
    "COMPREHENSIVE_REFINE_TEMPLATE",
    "get_prompt_templates",
    "get_tree_summarize_template",
]
