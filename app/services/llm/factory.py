from app.services.llm.base import LLMProvider
from app.services.llm.openai_adapter import OpenAIAdapter
from app.services.llm.gemini_adapter import GeminiAdapter
from app.services.llm.claude_adapter import ClaudeAdapter

class LLMFactory:
    """
    The Factory is responsible for selecting the right AI Provider
    based on the requested model string.
    """
    
    @staticmethod
    def get_provider(model: str) -> LLMProvider:
        model_id = model.lower()

        if model_id.startswith("gpt"):
            return OpenAIAdapter()
        
        elif model_id.startswith("gemini"):
            return GeminiAdapter()
        
        elif model_id.startswith("claude"):
            return ClaudeAdapter()
        
        else:
            raise ValueError(f"Unsupported AI Model: {model}")

    @staticmethod
    def get_all_models():
        """
        Helper to return a list of all supported models for the Frontend.
        """
        return [
            # OpenAI
            "gpt-5.2-pro", 
            "gpt-5.2", 
            "gpt-5-mini",
            
            # Google
            "gemini-2.5-pro", 
            "gemini-2.5-flash", 
            "gemini-3-pro-preview", 
            "gemini-3-flash-preview",

            # Anthropic
            "claude-4.5-opus",
            "claude-4.5-sonnet",
            "claude-4.5-haiku"
        ]