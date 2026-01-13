import json
import openai
from decimal import Decimal
from typing import AsyncGenerator, List, Dict
from app.core.config import settings
from app.services.llm.base import LLMProvider, PromptType
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage

class OpenAIAdapter(LLMProvider):
    _client: openai.AsyncOpenAI | None = None

    # 4X Profit Margin
    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        if not OpenAIAdapter._client:
            OpenAIAdapter._client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY
            )
        self.client = OpenAIAdapter._client

        # Pricing (USD per 1M tokens)
        self.pricing = {
            "gpt-5.2-pro": {"input": Decimal("5.00"), "output": Decimal("15.00")},
            "gpt-5.2": {"input": Decimal("2.50"), "output": Decimal("10.00")},
            "gpt-5-mini": {"input": Decimal("0.15"), "output": Decimal("0.60")},
        }

    def calculate_cost(self, usage: Usage, model: str) -> Decimal:
        """
        Calculates Price to User (Cost * Margin).
        Returns Decimal for high precision.
        """
        price_tier = self.pricing.get(model, self.pricing["gpt-5.2"])
        
        # Calculate Base Provider Cost
        input_cost = (Decimal(usage.prompt_tokens) / Decimal("1000000")) * price_tier["input"]
        output_cost = (Decimal(usage.completion_tokens) / Decimal("1000000")) * price_tier["output"]
        
        base_cost = input_cost + output_cost
        
        # Apply Profit Margin
        total_price_in_usd = base_cost * self.PROFIT_MARGIN

        # Convert USD to Credits
        total_price_to_user = total_price_in_usd * self.USD_TO_CREDITS_RATE
        
        # Round to 6 decimal places to match DB
        return total_price_to_user.quantize(Decimal("0.000001"))

    def _to_openai_messages(self, prompt: PromptType) -> List[Dict[str, str]]:
        messages = []
        if isinstance(prompt, str):
            return [{"role": "user", "content": prompt}]

        for item in prompt:
            if isinstance(item, ChatMessage):
                role = "assistant" if item.role == "ai" else item.role
                content = "".join(b.text for b in item.content)
                messages.append({"role": role, "content": content})
            elif isinstance(item, dict):
                role = "assistant" if item.get("role") == "ai" else item.get("role", "user")
                messages.append({"role": role, "content": item.get("content", "")})
                
        return messages

    async def generate_stream(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> AsyncGenerator[str, None]:
        
        openai_messages = self._to_openai_messages(prompt)
        # Fallback logic for model name
        api_model = model if model in self.pricing else "gpt-5.2-mini"

        stream = await self.client.chat.completions.create(
            model=api_model,
            messages=openai_messages,
            stream=True,
            stream_options={"include_usage": True}
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

            if chunk.usage:
                usage.prompt_tokens = chunk.usage.prompt_tokens
                usage.completion_tokens = chunk.usage.completion_tokens

    async def generate_text(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> str:
        openai_messages = self._to_openai_messages(prompt)
        api_model = model if model in self.pricing else "gpt-5.2-mini"
        
        response = await self.client.chat.completions.create(
            model=api_model,
            messages=openai_messages,
            stream=False
        )
        
        if response.usage:
            usage.prompt_tokens = response.usage.prompt_tokens
            usage.completion_tokens = response.usage.completion_tokens
            
        return response.choices[0].message.content or ""