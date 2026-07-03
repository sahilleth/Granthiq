from loguru import logger
from langfuse import observe
from src.services.generation.generators.base import BaseContentGenerator
from src.schemas.content import PodcastScript
from src.services.generation.prompts import PODCAST_PROMPT_TEMPLATE

class PodcastGenerator(BaseContentGenerator[PodcastScript]):
    @observe(as_type="generation")
    async def generate(self, context: str) -> PodcastScript:
        logger.info("Generating Podcast...")
        try:
            clean_context = context[:20000]
            
            return await self._generate_structured(
                prompt_template=PODCAST_PROMPT_TEMPLATE,
                output_cls=PodcastScript,
                context=clean_context
            )
        except Exception as e:
            logger.error(f"Failed to generate podcast: {e}")
            raise e
    
  