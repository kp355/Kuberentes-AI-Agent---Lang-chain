"""AI Client Factory with correct Gemini OpenAI-compatible support."""

from typing import Optional, List, Any, Dict
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from models.config import config
import structlog

logger = structlog.get_logger()


class AIClientFactory:
    """Factory for creating LLM clients with fallback support."""
    
    def __init__(self):
        self.config = config.llm
        self.primary_client: Optional[BaseChatModel] = None
        self.fallback_clients: List[BaseChatModel] = []
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize primary and fallback LLM clients."""
        providers = [self.config.primary_provider] + self.config.fallback_providers
        
        for provider in providers:
            try:
                client = self._create_client(provider)
                if client:
                    if self.primary_client is None:
                        self.primary_client = client
                        logger.info("Primary LLM client initialized", provider=provider)
                    else:
                        self.fallback_clients.append(client)
                        logger.info("Fallback LLM client initialized", provider=provider)
            except Exception as e:
                logger.warning(f"Failed to initialize {provider} client", error=str(e))
    
    def _create_client(self, provider: str) -> Optional[BaseChatModel]:
        """Create a specific LLM client based on provider."""
        try:
            if provider == "gemini":
                if not self.config.gemini_api_key:
                    logger.warning("Gemini API key not found")
                    return None
                
                logger.info("Creating Gemini client via OpenAI-compatible endpoint")

                # IMPORTANT: ChatOpenAI works correctly with Gemini's OpenAI-compatible API
                return ChatOpenAI(
                    model=self.config.gemini_model,
                    api_key=self.config.gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    temperature=self.config.gemini_temperature,
                    max_tokens=self.config.gemini_max_tokens,
                )
            
            elif provider == "openai":
                if not self.config.openai_api_key:
                    logger.warning("OpenAI API key not found")
                    return None
                
                return ChatOpenAI(
                    model=self.config.openai_model,
                    api_key=self.config.openai_api_key,
                    temperature=self.config.gemini_temperature,
                )
            
            elif provider == "anthropic":
                if not self.config.anthropic_api_key:
                    logger.warning("Anthropic API key not found")
                    return None
                
                return ChatAnthropic(
                    model=self.config.anthropic_model,
                    api_key=self.config.anthropic_api_key,
                    temperature=self.config.gemini_temperature,
                )
            
            else:
                logger.warning(f"Unknown provider: {provider}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating {provider} client", error=str(e))
            return None
    
    def get_client(self) -> BaseChatModel:
        """Get the primary LLM client."""
        if not self.primary_client:
            raise ValueError("No LLM client available. Check API keys in .env file.")
        return self.primary_client
    
    def get_client_with_fallback(self) -> List[BaseChatModel]:
        """Get all available clients (primary + fallbacks)."""
        clients = []
        if self.primary_client:
            clients.append(self.primary_client)
        clients.extend(self.fallback_clients)
        return clients


# Global AI client factory instance
ai_factory = AIClientFactory()


def get_llm() -> BaseChatModel:
    """Get the primary LLM client."""
    return ai_factory.get_client()
