# app/services/llm/schema.py
from typing import Literal, List
from pydantic import BaseModel

Role = Literal["system", "user", "assistant", "ai"]

class ContentBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ChatMessage(BaseModel):
    role: Role
    content: List[ContentBlock]

    @staticmethod
    def from_text(role: str, text: str) -> "ChatMessage":
        """
        Factory method to create a ChatMessage from raw strings.
        Accepts 'role' as a string (e.g. 'ai') and validates it against the Role type.
        """
        return ChatMessage(
            role=role,
            content=[ContentBlock(text=text)]
        )

    def to_openai_format(self):
        """
        Helper: Converts 'ai' back to 'assistant' ONLY when sending to OpenAI/LLMs
        that might be strict about role names.
        """
        role_str = "assistant" if self.role == "ai" else self.role
        return {"role": role_str, "content": self.content[0].text}