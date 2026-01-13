from abc import ABC, abstractmethod
from typing import AsyncGenerator, Union, List, Dict, Any
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage

PromptType = Union[str, List[ChatMessage], List[Dict[str, str]]]

class LLMProvider(ABC):
    """
    Abstract Base Class that defines the contract for all AI Adapters.
    Ensures OpenAI, Gemini, and Claude adapters all behave identically.
    """

    @abstractmethod
    async def generate_stream(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> AsyncGenerator[str, None]:
        """
        Yields text chunks for real-time streaming.
        Must update the `usage` object in-place.
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> str:
        """
        Returns the full response as a single string (non-streaming).
        """
        pass

    @abstractmethod
    def calculate_cost(self, usage: Usage, model: str) -> float:
        """
        Calculates the cost based on token usage.
        Returns the cost as a float representing micro-cents.
        """
        pass