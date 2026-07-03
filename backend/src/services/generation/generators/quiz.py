from loguru import logger
from langfuse import observe
from src.services.generation.generators.base import BaseContentGenerator
from src.schemas.content import Quiz
from src.services.generation.prompts import QUIZ_PROMPT_TEMPLATE

class QuizGenerator(BaseContentGenerator[Quiz]):
    @observe(as_type="generation")
    async def generate(self, context: str) -> Quiz:
        logger.info("Generating Quiz...")
        try:
            # Clean context to prevent token overflow if necessary
            clean_context = context[:20000] # Safety clip
            
            return await self._generate_structured(
                prompt_template=QUIZ_PROMPT_TEMPLATE,
                output_cls=Quiz,
                context=clean_context
            )
        except Exception as e:
            logger.error(f"Failed to generate quiz: {e}")
            raise e
