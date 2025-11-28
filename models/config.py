"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import Optional, List
import yaml
from pathlib import Path


class LLMConfig(BaseSettings):
    """LLM Provider Configuration."""
    primary_provider: str = "gemini"
    fallback_providers: List[str] = ["openai", "anthropic"]
    
    # Gemini
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash-exp"
    gemini_temperature: float = 0.1
    gemini_max_tokens: int = 8192
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4-turbo-preview"
    
    # Anthropic
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


class KubernetesConfig(BaseSettings):
    """Kubernetes Configuration."""
    kubeconfig_path: Optional[str] = None
    s3_bucket_name: Optional[str] = None
    s3_kubeconfig_key: Optional[str] = None
    max_log_lines: int = 500
    event_lookback_hours: int = 24
    
    class Config:
        env_file = ".env"


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


class Config:
    """Main configuration class."""
    
    def __init__(self):
        self.app = AppConfig()
        self.llm = LLMConfig()
        self.kubernetes = KubernetesConfig()
        
        # Load YAML config if exists
        self._load_yaml_config()
    
    def _load_yaml_config(self):
        """Load additional configuration from YAML file."""
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
            # Override with YAML values if present
            if 'llm' in yaml_config:
                for key, value in yaml_config['llm'].items():
                    if hasattr(self.llm, key):
                        setattr(self.llm, key, value)


# Global config instance
config = Config()
