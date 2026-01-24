from typing import Literal, List, Optional
from pydantic import BaseModel

Role = Literal["system", "user", "assistant", "ai"]

class ContentBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class Attachment(BaseModel):
    """
    Represents a processed file ready for LLM consumption.
    - type: 'text' (for parsed PDFs/code) or 'image' (for base64 images)
    - content: The actual text string or base64 data string
    - mime_type: Required for images (e.g. 'image/jpeg')
    """
    type: Literal["text", "image"]
    content: str
    mime_type: Optional[str] = None

class ChatMessage(BaseModel):
    role: Role
    content: List[ContentBlock]
    attachments: Optional[List[Attachment]] = []

    @staticmethod
    def from_text(role: str, text: str) -> "ChatMessage":
        """
        Factory method to create a ChatMessage from raw strings.
        Accepts 'role' as a string (e.g. 'ai') and validates it against the Role type.
        """
        return ChatMessage(
            role=role,
            content=[ContentBlock(text=text)],
            attachments=[]
        )

    def to_openai_format(self):
        """
        Helper: Converts internal structure to OpenAI API format.
        - Handles Role mapping ('ai' -> 'assistant').
        - Handles Multimodal content (mixing text + images).
        """
        role_str = "assistant" if self.role == "ai" else self.role

        # If no attachments, send standard string content (simple format)
        if not self.attachments:
            # Join all text blocks into one string
            full_text = "".join(b.text for b in self.content)
            return {"role": role_str, "content": full_text}

        # If attachments exist, switch to "content parts" format (multimodal)
        content_parts = []

        # Add the main text content first
        text_content = "".join(b.text for b in self.content)
        if text_content:
            content_parts.append({"type": "text", "text": text_content})

        # Append attachments
        for attachment in self.attachments:
            if attachment.type == "text":
                # "Stuff" text attachments into the text prompt context
                if content_parts and content_parts[0]["type"] == "text":
                     content_parts[0]["text"] += f"\n\n{attachment.content}"
                else:
                     content_parts.append({"type": "text", "text": attachment.content})
            
            elif attachment.type == "image":
                # OpenAI Image Format
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment.mime_type};base64,{attachment.content}",
                        "detail": "auto"
                    }
                })

        return {"role": role_str, "content": content_parts}