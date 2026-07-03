from llama_index.core.llms import LLM
from llama_index.core.program import LLMTextCompletionProgram
from typing import Type, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class BaseContentGenerator(Generic[T]):
    def __init__(self, llm: LLM):
        self.llm = llm

    async def _generate_structured(self, prompt_template: str, output_cls: Type[T], **kwargs) -> T:
        """
        Robust structured generation using LLMTextCompletionProgram.
        """
        program = LLMTextCompletionProgram.from_defaults(
            output_cls=output_cls,
            prompt_template_str=prompt_template,
            llm=self.llm,
            verbose=True,
        )
        output = await program.acall(**kwargs)
        return output
