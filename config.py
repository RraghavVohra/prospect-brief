"""App settings, loaded once from environment variables (or a .env file)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    # Main reasoner (the brain of the ReAct loop)
    reasoner_model: str = os.getenv("REASONER_MODEL", "gpt-5.6-luna")
    reasoner_max_tokens: int = 32000

    # Model behind the web_search tool
    search_model: str = os.getenv("SEARCH_MODEL", "gpt-5.6-luna")

    # Max Reason -> Act -> Observe cycles before we force the brief to be written
    max_steps: int = int(os.getenv("MAX_STEPS", "8"))


settings = Settings()
