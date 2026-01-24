import base64
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
            "gemini-3-pro-preview": {
                "input": Decimal("3.00"),
                "output": Decimal("15.00"),
            },
            "gemini-2.5-pro": {
                "input": Decimal("1.88"),
                "output": Decimal("12.50"),
            },
            "gemini-3-flash-preview": {
                "input": Decimal("0.50"),
                "output": Decimal("3.00"),
            },
            "gemini-2.5-flash": {
                "input": Decimal("0.30"),
                "output": Decimal("2.50"),
            },
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
            parts = []

            # 1. Extract Role
            if isinstance(item, ChatMessage):
                role = item.role
            elif isinstance(item, dict):
                role = item.get("role", "user")

            # 2. Build Parts from Content & Attachments
            if isinstance(item, ChatMessage):
                # Add main text content
                text_content = "".join(b.text for b in item.content)
                if text_content:
                    parts.append(types.Part.from_text(text=text_content))
                
                # Add Attachments
                if item.attachments:
                    for att in item.attachments:
                        if att.type == "text":
                            # Combine text attachments into a text part
                            parts.append(types.Part.from_text(text=f"\n[Attachment: {att.content}]"))
                        elif att.type == "image":
                            # Decode base64 string to bytes for Gemini SDK
                            img_bytes = base64.b64decode(att.content)
                            parts.append(types.Part.from_bytes(
                                data=img_bytes, 
                                mime_type=att.mime_type or "image/jpeg"
                            ))
            elif isinstance(item, dict):
                # Fallback for dict-based prompt
                content_text = item.get("content", "")
                if content_text:
                    parts.append(types.Part.from_text(text=content_text))

            # 3. Assign to Role
            if role == "system":
                # System instructions are text-only in this simplified adapter
                for p in parts:
                    if p.text:
                        system_parts.append(p.text)
            elif role == "user":
                if parts:
                    contents_list.append(types.Content(role="user", parts=parts))
            elif role in ["ai", "assistant", "model"]:
                if parts:
                    contents_list.append(types.Content(role="model", parts=parts))

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