from google import genai
from google.genai import types
from decimal import Decimal
from typing import AsyncGenerator, List, Tuple
from app.core.config import settings
from app.services.llm.base import LLMProvider, PromptType
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage

class GeminiAdapter(LLMProvider):
    _client: genai.Client | None = None
    
    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        if not GeminiAdapter._client:
            GeminiAdapter._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.client = GeminiAdapter._client

        # Pricing (USD per 1M tokens)
        self.pricing = {
            "gemini-2.5-pro": {"input": Decimal("3.50"), "output": Decimal("10.50")},
            "gemini-3-pro-preview": {"input": Decimal("3.50"), "output": Decimal("10.50")},
            "gemini-3-flash-preview": {"input": Decimal("0.35"), "output": Decimal("1.05")},
            "gemini-2.5-flash": {"input": Decimal("0.35"), "output": Decimal("1.05")},
        }

    def calculate_cost(self, usage: Usage, model: str) -> Decimal:
        """
        Calculates Price to User (Cost * Margin).
        """
        price_tier = self.pricing.get(model, self.pricing["gemini-3-flash-preview"])
        
        input_cost = (Decimal(usage.prompt_tokens) / Decimal("1000000")) * price_tier["input"]
        output_cost = (Decimal(usage.completion_tokens) / Decimal("1000000")) * price_tier["output"]
        
        base_cost = input_cost + output_cost
        total_price_in_usd = base_cost * self.PROFIT_MARGIN
        total_price_to_user = total_price_in_usd * self.USD_TO_CREDITS_RATE
        
        return total_price_to_user.quantize(Decimal("0.000001"))

    def _prepare_gemini_request(self, prompt: PromptType) -> Tuple[str | None, List[types.Content]]:
        system_parts = []
        contents_list = []
        items = []

        if isinstance(prompt, str):
            return None, [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ]
        else:
            items = prompt

        for item in items:
            role = ""
            content_text = ""

            if isinstance(item, ChatMessage):
                role = item.role
                content_text = "".join(b.text for b in item.content)
            elif isinstance(item, dict):
                role = item.get("role", "user")
                content_text = item.get("content", "")

            if role == "system":
                system_parts.append(content_text)
            elif role == "user":
                contents_list.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=content_text)])
                )
            elif role in ["ai", "assistant", "model"]:
                contents_list.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=content_text)])
                )

        system_instruction = "\n".join(system_parts) if system_parts else None
        return system_instruction, contents_list

    async def generate_stream(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> AsyncGenerator[str, None]:
        
        system_inst, contents = self._prepare_gemini_request(prompt)
        config = types.GenerateContentConfig(
            system_instruction=system_inst
        ) if system_inst else None

        # Count Tokens
        try:
            count_resp = await self.client.aio.models.count_tokens(
                model=model,
                contents=contents
            )
            usage.prompt_tokens = count_resp.total_tokens
        except Exception:
            pass

        response_stream = await self.client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config
        )

        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text

            if chunk.usage_metadata:
                usage.completion_tokens = chunk.usage_metadata.candidates_token_count
                if usage.prompt_tokens == 0:
                    usage.prompt_tokens = chunk.usage_metadata.prompt_token_count

    async def generate_text(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> str:
        system_inst, contents = self._prepare_gemini_request(prompt)
        config = types.GenerateContentConfig(
            system_instruction=system_inst
        ) if system_inst else None

        try:
            count_resp = await self.client.aio.models.count_tokens(
                model=model,
                contents=contents
            )
            usage.prompt_tokens = count_resp.total_tokens
        except Exception:
            pass

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
        
        if response.usage_metadata:
            usage.completion_tokens = response.usage_metadata.candidates_token_count
            
        return response.text or ""