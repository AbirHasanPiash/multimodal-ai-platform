from dataclasses import dataclass
import math

@dataclass
class Usage:
    """
    Mutable container for token usage statistics.
    passed by reference to LLM Providers.
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def ensure_validity(self, prompt_text: str, completion_text: str):
        """
        Fallback mechanism:
        If the API failed to report tokens (count is 0), 
        estimate them based on character count (approx 4 chars per token).
        This prevents billing leaks.
        """
        if self.prompt_tokens == 0 and prompt_text:
            self.prompt_tokens = math.ceil(len(prompt_text) / 4)
            
        if self.completion_tokens == 0 and completion_text:
            self.completion_tokens = math.ceil(len(completion_text) / 4)