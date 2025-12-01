"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file explicitly at module load time
load_dotenv()


class LLMConfig(BaseSettings):
    """LLM Provider Configuration."""
    primary_provider: str = "gemini"
    fallback_providers: List[str] = ["openai", "anthropic"]
    
    # Gemini - Use Field with alias for env var mapping
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = "gemini-2.0-flash"  # Latest model
    gemini_temperature: float = 0.1
    gemini_max_tokens: int = 8192
    
    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4-turbo-preview"
    
    # Anthropic
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    class Config:
        env_file = ".env"
        extra = "ignore"
        populate_by_name = True


class KubernetesConfig(BaseSettings):
    """Kubernetes Configuration."""
    kubeconfig_path: Optional[str] = Field(default=None, alias="KUBECONFIG_PATH")
    s3_bucket_name: Optional[str] = Field(default=None, alias="S3_BUCKET_NAME")
    s3_kubeconfig_key: Optional[str] = Field(default=None, alias="S3_KUBECONFIG_KEY")
    max_log_lines: int = 500
    event_lookback_hours: int = 24
    
    class Config:
        env_file = ".env"
        extra = "ignore"
        populate_by_name = True


class AppConfig(BaseSettings):
    """Application Configuration."""
    app_name: str = "Kubernetes AI Troubleshooter"
    app_version: str = "2.0.0"
    environment: str = "production"
    log_level: str = "INFO"
    
    # CORS
    cors_origins: List[str] = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"


class Config:
    """Main configuration class."""
    
    def __init__(self):
        self.app = AppConfig()
        self.llm = LLMConfig()
        self.kubernetes = KubernetesConfig()
        
        # Load YAML config if exists
        self._load_yaml_config()
        
        # Also check environment directly for API keys
        self._load_env_overrides()
    
    def _load_yaml_config(self):
        """Load additional configuration from YAML file."""
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
            # Override with YAML values if present
            if yaml_config and 'llm' in yaml_config:
                llm_config = yaml_config['llm']
                if 'gemini' in llm_config:
                    gemini_config = llm_config['gemini']
                    if 'model' in gemini_config:
                        self.llm.gemini_model = gemini_config['model']
                    if 'temperature' in gemini_config:
                        self.llm.gemini_temperature = gemini_config['temperature']
                    if 'max_tokens' in gemini_config:
                        self.llm.gemini_max_tokens = gemini_config['max_tokens']
    
    def _load_env_overrides(self):
        """Load API keys directly from environment if not set."""
        if not self.llm.gemini_api_key:
            self.llm.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not self.llm.openai_api_key:
            self.llm.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.llm.anthropic_api_key:
            self.llm.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")


# Global config instance
config = Config()
