from loguru import logger
from langfuse import observe
from src.services.generation.generators.base import BaseContentGenerator
from src.schemas.content import FlashcardDeck
from src.services.generation.prompts import FLASHCARD_PROMPT_TEMPLATE

class FlashcardGenerator(BaseContentGenerator[FlashcardDeck]):
    @observe(as_type="generation")
    async def generate(self, context: str) -> FlashcardDeck:
        logger.info("Generating Flashcards...")
        try:
            clean_context = context[:20000]
            
            return await self._generate_structured(
                prompt_template=FLASHCARD_PROMPT_TEMPLATE,
                output_cls=FlashcardDeck,
                context=clean_context
            )
        except Exception as e:
            logger.error(f"Failed to generate flashcards: {e}")
            raise e
