from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config(BaseSettings):
    SAMBANOVA_API_KEY: Optional[str] = None
    SAMBANOVA_BASE_URL: Optional[str] = None
    LLM_REASONING: Optional[str] = None
    LLM_REGULAR: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    DEEPSEEK_BASE_URL: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL_REASON: Optional[str] = None
    DEEPSEEK_MODEL_CHAT: Optional[str] = None

config = Config()