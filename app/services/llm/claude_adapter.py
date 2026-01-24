import anthropic
from decimal import Decimal
from typing import AsyncGenerator, List, Dict, Tuple, Any
from app.core.config import settings
from app.services.llm.base import LLMProvider, PromptType
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage

class ClaudeAdapter(LLMProvider):
    _client: anthropic.AsyncAnthropic | None = None
    
    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        if not ClaudeAdapter._client:
            ClaudeAdapter._client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        self.client = ClaudeAdapter._client

        self.pricing = {
            "claude-4.5-opus":   {"input": Decimal("5.00"),  "output": Decimal("25.00")},
            "claude-4.5-sonnet": {"input": Decimal("3.00"),  "output": Decimal("15.00")},
            "claude-4.5-haiku":  {"input": Decimal("1.00"),  "output": Decimal("5.00")},
        }

        
        self.model_mapping = {
            "claude-4.5-opus": "claude-opus-4-5-20251101",
            "claude-4.5-sonnet": "claude-sonnet-4-5-20250929",
            "claude-4.5-haiku": "claude-haiku-4-5-20251001",
        }

    def calculate_cost(self, usage: Usage, model: str) -> Decimal:
        """
        Calculates Price to User (Cost * Margin).
        """
        price_tier = self.pricing.get(model, self.pricing["claude-4.5-sonnet"])
        
        input_cost = (Decimal(usage.prompt_tokens) / Decimal("1000000")) * price_tier["input"]
        output_cost = (Decimal(usage.completion_tokens) / Decimal("1000000")) * price_tier["output"]
        
        base_cost = input_cost + output_cost
        total_price_in_usd = base_cost * self.PROFIT_MARGIN
        total_price_to_user = total_price_in_usd * self.USD_TO_CREDITS_RATE

        return total_price_to_user.quantize(Decimal("0.000001"))

    def _prepare_claude_request(self, prompt: PromptType) -> Tuple[str, List[Dict[str, Any]]]:
        system_prompt = ""
        messages = []
        items = []

        if isinstance(prompt, str):
            return "", [{"role": "user", "content": prompt}]
        else:
            items = prompt

        for item in items:
            role = ""
            content_blocks: List[Dict[str, Any]] = []

            # 1. Parse Input Item
            if isinstance(item, ChatMessage):
                role = item.role
                
                # Add Attachments first (Images then Text)
                if item.attachments:
                    for att in item.attachments:
                        if att.type == "image":
                            content_blocks.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": att.mime_type or "image/jpeg",
                                    "data": att.content
                                }
                            })
                        elif att.type == "text":
                            content_blocks.append({
                                "type": "text",
                                "text": f"<file_context>\n{att.content}\n</file_context>"
                            })
                
                # Add main text
                text_body = "".join(b.text for b in item.content)
                if text_body:
                    content_blocks.append({
                        "type": "text", 
                        "text": text_body
                    })

            elif isinstance(item, dict):
                role = item.get("role", "user")
                text_content = item.get("content", "")
                if text_content:
                    content_blocks.append({"type": "text", "text": text_content})

            # 2. Assign to specific role
            if role == "system":
                # Claude handles system prompt via top-level parameter
                for block in content_blocks:
                    if block["type"] == "text":
                        system_prompt += block["text"] + "\n"
            
            elif role == "user":
                if content_blocks:
                    messages.append({"role": "user", "content": content_blocks})
            
            elif role in ["ai", "assistant"]:
                if content_blocks:
                    messages.append({"role": "assistant", "content": content_blocks})

        return system_prompt.strip(), messages

    def _get_api_model_id(self, model: str) -> str:
        return self.model_mapping.get(model, "claude-sonnet-4-5-20250929")

    async def generate_stream(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> AsyncGenerator[str, None]:
        
        system_prompt, messages = self._prepare_claude_request(prompt)
        api_model = self._get_api_model_id(model)

        async with self.client.messages.stream(
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            model=api_model,
        ) as stream:
            
            async for text in stream.text_stream:
                yield text

            final_message = await stream.get_final_message()
            if final_message.usage:
                usage.prompt_tokens = final_message.usage.input_tokens
                usage.completion_tokens = final_message.usage.output_tokens

    async def generate_text(
        self,
        prompt: PromptType,
        model: str,
        usage: Usage
    ) -> str:
        system_prompt, messages = self._prepare_claude_request(prompt)
        api_model = self._get_api_model_id(model)

        response = await self.client.messages.create(
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            model=api_model,
        )

        if response.usage:
            usage.prompt_tokens = response.usage.input_tokens
            usage.completion_tokens = response.usage.output_tokens

        if response.content:
            return "".join(block.text for block in response.content if block.type == "text")
        return ""