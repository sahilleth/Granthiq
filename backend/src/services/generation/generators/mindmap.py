from loguru import logger
from langfuse import observe
from src.services.generation.generators.base import BaseContentGenerator
from src.schemas.content import MindMap
from src.services.generation.prompts import MINDMAP_PROMPT_TEMPLATE

class MindMapGenerator(BaseContentGenerator[MindMap]):
    @observe(as_type="generation")
    async def generate(self, context: str) -> MindMap:
        logger.info("Generating MindMap...")
        try:
            clean_context = context[:20000]
            
            return await self._generate_structured(
                prompt_template=MINDMAP_PROMPT_TEMPLATE,
                output_cls=MindMap,
                context=clean_context
            )
        except Exception as e:
            logger.error(f"Failed to generate mindmap: {e}")
            raise e
