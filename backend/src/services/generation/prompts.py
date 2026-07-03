PODCAST_PROMPT_TEMPLATE = """
Generate a lively, engaging podcast script based on the provided context.
Host (Jane): Curious, asks good questions, enthusiastic.
Expert (Tom): Knowledgeable, uses analogies, explains clearly.

CONTEXT:
\"\"\"
{context}
\"\"\"

REQUIREMENTS:
- Start with a catchy intro.
- Keep turns short and conversational.
- Include moments of confusion where the Host misunderstands and the Expert corrects them gently.
- Use natural fillers like "Wait, back up", "So you mean...", or "That's wild".
- Ensure the conversation flows naturally and isn't just a lecture.
- STRICTLY output valid JSON. No markdown formatting.
"""

QUIZ_PROMPT_TEMPLATE = """
Generate a challenging quiz based on the context.

CONTEXT:
\"\"\"
{context}
\"\"\"

REQUIREMENTS:
- 5 multiple-choice questions.
- 4 options per question.
- Include reasoning for the correct answer.
- Focus on the NOVEL contributions, specific findings, or unique arguments of this specific document.
- Do NOT ask generic definitions or surface-level questions.
- STRICTLY output valid JSON.
"""

FLASHCARD_PROMPT_TEMPLATE = """
Generate 10 study flashcards based on the context.

CONTEXT:
\"\"\"
{context}
\"\"\"

REQUIREMENTS:
- Front: Specific question/concept.
- Back: Concise definition (max 2 sentences).
- Focus on the NOVEL contributions of this specific document. 
- Do not ask generic definitions (e.g., "What is X?"). 
- Ask about specific findings, numbers, or arguments made in the text.
"""

MINDMAP_PROMPT_TEMPLATE = """
Generate a hierarchical mind map structure.

CONTEXT:
\"\"\"
{context}
\"\"\"

REQUIREMENTS:
- Root node: MUST be the exact title or main subject of the document.
- 3-4 levels deep.
- Keep labels short (2-5 words).
- Break down the document into its main logical sections (e.g. Methodology, Results, Implications).
"""
