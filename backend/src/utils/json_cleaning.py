from typing import Any, Dict, List, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from loguru import logger


class JSONCleaningLLM(BaseChatModel):
    """Wrapper that cleans markdown code blocks from LLM responses."""
    
    llm: Any  # The underlying LLM
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, llm, **kwargs):
        super().__init__(llm=llm, **kwargs)
    
    @staticmethod
    def clean_json_response(text: str) -> str:
        """Remove markdown code blocks from JSON output."""
        if not text:
            return text
        
        original_text = text
        text = text.strip()
        # Remove ```json and ``` wrapping
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line if it's ```json or ```
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        return text
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate and clean responses."""
        result = self.llm._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        
        # Clean all generations
        for generation in result.generations:
            # Handle ChatGeneration (has message field)
            if hasattr(generation, 'message'):
                original_content = generation.message.content
                cleaned_text = self.clean_json_response(original_content)
                
                # Check if cleaning actually happened
                if original_content != cleaned_text:
                    logger.debug(f"Cleaning JSON response (Sync): Removed markdown wrapping")
                
                # Update message content
                generation.message = AIMessage(content=cleaned_text)
                
                # EXPLICITLY Update text field too (RAGAS might check this)
                generation.text = cleaned_text
                
            # Handle standard Generation (has text field)
            elif hasattr(generation, 'text'):
                original_text = generation.text
                cleaned_text = self.clean_json_response(original_text)
                generation.text = cleaned_text
        
        return result
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate and clean responses."""
        result = await self.llm._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        
        # Clean all generations
        for generation in result.generations:
            # Handle ChatGeneration (has message field)
            if hasattr(generation, 'message'):
                original_content = generation.message.content
                cleaned_text = self.clean_json_response(original_content)
                
                # Check if cleaning actually happened
                if original_content != cleaned_text:
                    logger.debug(f"Cleaning JSON response (Async): Removed markdown wrapping")
                
                # Update message content
                generation.message = AIMessage(content=cleaned_text)
                
                # EXPLICITLY Update text field too
                generation.text = cleaned_text
                
            # Handle standard Generation (has text field)
            elif hasattr(generation, 'text'):
                original_text = generation.text
                cleaned_text = self.clean_json_response(original_text)
                generation.text = cleaned_text
        
        return result
    
    @property
    def _llm_type(self) -> str:
        return f"json_cleaning_{getattr(self.llm, '_llm_type', 'unknown')}"
    
    @property  
    def _identifying_params(self) -> Dict[str, Any]:
        """Get identifying parameters."""
        return {"llm": self.llm}
