import io
import base64
from pathlib import Path
from fastapi import UploadFile, HTTPException
from PIL import Image
import PyPDF2

# Try importing docx, handle gracefully if missing
try:
    import docx
except ImportError:
    docx = None

MAX_IMAGE_SIZE = 1024 * 1024 * 4  # 4MB limit for processing
MAX_TEXT_LENGTH = 100_000  # Character limit to prevent context overflow

# Whitelist of code extensions to treat as text, even if MIME is generic
CODE_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.c', '.cpp', '.h', '.hpp', 
    '.java', '.rs', '.go', '.rb', '.php', '.sh', '.bat', '.ps1', 
    '.html', '.css', '.scss', '.sql', '.json', '.yaml', '.yml', 
    '.xml', '.md', '.txt', '.env', '.gitignore', '.dockerfile', '.conf', '.ini'
}

async def process_file(file: UploadFile) -> dict:
    """
    Reads a file and returns a dictionary with 'type' and 'content'.
    Content is either raw text or a base64 image string.
    """
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename
    file_ext = Path(filename).suffix.lower()
    
    # Read file into memory
    file_bytes = await file.read()
    
    try:
        # Handle Images
        if content_type.startswith("image/"):
            return _process_image(file_bytes, content_type)
        
        # Handle PDFs
        elif content_type == "application/pdf" or file_ext == ".pdf":
            text = _extract_pdf_text(file_bytes)
            return _wrap_text_content(filename, text)

        # Handle Word Docs (.docx)
        elif file_ext == ".docx":
            text = _extract_docx_text(file_bytes)
            return _wrap_text_content(filename, text)

        # Handle Text / Code / JSON / CSV
        # We check specific text mime types OR if the extension is a known code file
        is_text_mime = (
            content_type.startswith("text/") or 
            "json" in content_type or 
            "javascript" in content_type or
            "xml" in content_type
        )
        
        if is_text_mime or file_ext in CODE_EXTENSIONS or file_ext == ".csv":
            text = _decode_text(file_bytes)
            return _wrap_text_content(filename, text)

        # Unsupported
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {content_type} ({file_ext})"
            )
            
    except Exception as e:
        # Catch unexpected processing errors to prevent server crash
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

def _wrap_text_content(filename: str, text: str) -> dict:
    """Helper to format text output consistently"""
    return {
        "type": "text",
        "content": f"--- START FILE: {filename} ---\n{text[:MAX_TEXT_LENGTH]}\n--- END FILE ---",
        "filename": filename
    }

def _decode_text(file_bytes: bytes) -> str:
    """Safely decode text with fallback for encoding issues"""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback to latin-1 which rarely fails, or ignore errors
        try:
            return file_bytes.decode("latin-1")
        except Exception:
            return file_bytes.decode("utf-8", errors="replace")

def _process_image(file_bytes: bytes, mime_type: str) -> dict:
    """Resize image if too large and convert to base64"""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        
        # Resize if dimension is massive (to save tokens/bandwidth)
        max_dim = 2048
        if image.width > max_dim or image.height > max_dim:
            image.thumbnail((max_dim, max_dim))
            
        # Convert back to bytes
        buffer = io.BytesIO()
        # Convert to RGB if saving as JPEG (removes alpha channel)
        if mime_type == "image/jpeg" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
            
        format_mapping = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
            "image/webp": "WEBP",
            "image/gif": "GIF"
        }
        save_format = format_mapping.get(mime_type, "PNG")
        
        image.save(buffer, format=save_format, optimize=True)
        
        # Base64 encode
        img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        return {
            "type": "image",
            "mime_type": mime_type,
            "content": img_str
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid image file")

def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        # Limit to first 20 pages to prevent context explosion
        for page in pdf_reader.pages[:20]: 
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text or "[PDF contained no readable text]"
    except Exception:
        return "[Error extracting PDF text]"

def _extract_docx_text(file_bytes: bytes) -> str:
    if docx is None:
        return "[Error: python-docx not installed on server]"
    
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)
    except Exception:
        return "[Error extracting Word document text]"