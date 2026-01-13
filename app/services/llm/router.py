from typing import Optional
import re

class ModelRouter:
    """
    Advanced Router to select the best AI model based on user intent scoring.
    """
    
    # Expanded Keyword Patterns
    
    CODING_PATTERNS = [
        # Core Syntax & Languages
        r"\b(def|class|import|function|const|let|var|return|await|async)\b",
        r"\b(struct|impl|interface|package|namespace|void|public|private)\b", # Java/C++/Rust/Go
        r"\b(python|javascript|typescript|golang|rust|java|c\+\+|swift|kotlin)\b",
        r"\b(bash|shell|powershell|zsh|chmod|sudo|grep|sed|awk)\b", # DevOps/Terminal
        
        # Web Frameworks & Libraries
        r"\b(react|vue|angular|svelte|next\.?js|nuxt|node\.?js|express)\b",
        r"\b(fastapi|django|flask|spring boot|laravel|rails|asp\.net)\b",
        r"\b(tailwind|bootstrap|css|sass|html|jsx|tsx|component)\b",
        r"\b(redux|zustand|context api|hooks|middleware|auth)\b",

        # Infrastructure & Tools
        r"\b(docker|kubernetes|k8s|aws|azure|gcp|terraform|ansible)\b",
        r"\b(git|github|gitlab|ci/cd|pipeline|jenkins|actions)\b",
        r"\b(npm|pip|yarn|cargo|maven|gradle|composer)\b",
        r"\b(linux|ubuntu|centos|debian|alpine|ssh|nginx|apache)\b",

        # Debugging & Concepts
        r"\b(bug|error|exception|stacktrace|traceback|undefined|null|segfault)\b",
        r"\b(refactor|optimize|complexity|big o|algorithm|structure)\b",
        r"\b(api|rest|graphql|grpc|websocket|endpoint|json|xml|yaml)\b",
        r"\b(db|database|sql|postgres|mysql|mongodb|redis|orm|sqlalchemy)\b"
    ]
    
    REASONING_PATTERNS = [
        # Math & Logic
        r"\b(solve|calculate|compute|prove|derive|evaluate)\b",
        r"\b(math|algebra|calculus|geometry|trigonometry|statistics|probability)\b",
        r"\b(logic|theorem|axiom|lemma|proof|contradiction|fallacy)\b",
        
        # Analysis & Strategy
        r"\b(analyze|critique|compare|contrast|pros and cons|trade-off)\b",
        r"\b(strategy|plan|roadmap|methodology|framework|approach)\b",
        r"\b(why|how does|explain|implication|consequence|causality)\b",
        r"\b(troubleshoot|diagnose|root cause|investigate)\b",

        # Science & Academic
        r"\b(physics|chemistry|biology|quantum|relativity|thermodynamics)\b",
        r"\b(research|hypothesis|experiment|study|citation|reference)\b",
        r"\b(economic|market|financial|investment|crypto|blockchain)\b"
    ]
    
    CREATIVE_PATTERNS = [
        # Writing Formats
        r"\b(write|compose|draft|create|generate|brainstorm)\b",
        r"\b(story|poem|essay|blog|article|email|letter|speech)\b",
        r"\b(script|screenplay|dialogue|lyrics|song|haiku|sonnet)\b",
        r"\b(tweet|post|caption|headline|tagline|slogan|copy)\b",

        # Narrative Elements
        r"\b(imagine|scenario|fiction|fantasy|sci-fi|plot|twist)\b",
        r"\b(character|protagonist|antagonist|setting|world-building)\b",
        r"\b(tone|style|voice|mood|atmosphere|metaphor|simile)\b",
        
        # Professional/Marketing
        r"\b(marketing|proposal|pitch|presentation|resume|cover letter)\b",
        r"\b(branding|identity|mission|vision|value proposition)\b"
    ]
    
    DATA_PATTERNS = [
        # Data Actions
        r"\b(summarize|summary|extract|key points|tl;dr|abstract)\b",
        r"\b(visualize|plot|chart|graph|dashboard|heatmap)\b",
        r"\b(clean|transform|process|parse|scrape|crawl)\b",
        
        # Data Formats & Tools
        r"\b(dataset|csv|excel|spreadsheet|dataframe|jsonl|parquet)\b",
        r"\b(pandas|numpy|matplotlib|seaborn|scikit|pytorch|tensorflow)\b",
        
        # Analysis Terms
        r"\b(pattern|trend|insight|correlation|outlier|anomaly)\b",
        r"\b(report|audit|review|assessment|log analysis)\b"
    ]

    @classmethod
    def _calculate_score(cls, text: str, patterns: list) -> int:
        score = 0
        text_lower = text.lower()
        for pattern in patterns:
            # Count how many times these patterns appear
            matches = re.findall(pattern, text_lower)
            score += len(matches)
        return score

    @classmethod
    def determine_model(cls, prompt: str, user_preference: Optional[str] = None) -> str:
        """
        Returns the Model ID to be used by the Factory.
        """

        # User Override
        if user_preference and user_preference.lower() != "auto":
            return user_preference

        # Score the Prompt
        coding_score = cls._calculate_score(prompt, cls.CODING_PATTERNS)
        reasoning_score = cls._calculate_score(prompt, cls.REASONING_PATTERNS)
        creative_score = cls._calculate_score(prompt, cls.CREATIVE_PATTERNS)
        data_score = cls._calculate_score(prompt, cls.DATA_PATTERNS)

        # Decision Logic

        # High Coding Intent -> Claude 4.5 Opus (Excellent at complex architecture & refactoring)
        if coding_score > 0 and coding_score >= max(reasoning_score, creative_score, data_score):
            return "claude-4.5-opus"

        # Heavy Data/Context -> Gemini 2.5 Pro (Massive Context Window)
        # Check if data score is high OR if the prompt is significantly long
        if (data_score > 0 and data_score >= max(reasoning_score, creative_score)) or len(prompt) > 4000:
            return "gemini-2.5-pro"
        
        # Deep Reasoning/Math -> GPT-5.2 Pro (Strong logical deduction)
        if reasoning_score > 0 and reasoning_score >= max(creative_score, data_score):
            return "gpt-5.2-pro"

        # Creative Writing -> Gemini 2.5 Pro (Often more fluid/imaginative)
        if creative_score > 0:
            return "gemini-2.5-pro"
            
        # 4. Fallback Logic based on Length
        
        # Very Short/Conversational -> Gemini 3 Flash (Fastest response time)
        if len(prompt) < 150:
            return "gemini-3-flash-preview"

        # Default Standard -> GPT-5.2 (Safe, balanced default)
        return "gpt-5.2"