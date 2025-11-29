"""Utility for loading kubeconfig from S3 or local file."""
import boto3
from pathlib import Path
import structlog
from models.config import config

logger = structlog.get_logger()


class KubeconfigLoader:
    """Load kubeconfig from S3 or local filesystem."""
    
    def __init__(self):
        self.s3_bucket = config.kubernetes.s3_bucket_name
        self.s3_key = config.kubernetes.s3_kubeconfig_key
        self.local_path = config.kubernetes.kubeconfig_path
    
    def load_kubeconfig(self) -> str:
        """Load kubeconfig and return path."""
        # Try local path first
        if self.local_path and Path(self.local_path).exists():
            logger.info("Using local kubeconfig", path=self.local_path)
            return self.local_path
        
        # Try S3 if configured
        if self.s3_bucket and self.s3_key:
            try:
                return self._download_from_s3()
            except Exception as e:
                logger.error("Failed to download kubeconfig from S3", error=str(e))
        
        # Fallback to default kubeconfig location
        default_path = str(Path.home() / ".kube" / "config")
        if Path(default_path).exists():
            logger.info("Using default kubeconfig", path=default_path)
            return default_path
        
        raise ValueError("No kubeconfig found. Set KUBECONFIG_PATH or configure S3 bucket.")
    
    def _download_from_s3(self) -> str:
        """Download kubeconfig from S3."""
        logger.info("Downloading kubeconfig from S3", bucket=self.s3_bucket, key=self.s3_key)
        
        s3 = boto3.client('s3')
        
        # Download to temp directory
        local_path = Path("/tmp") / "kubeconfig"
        s3.download_file(self.s3_bucket, self.s3_key, str(local_path))
        
        logger.info("Kubeconfig downloaded successfully")
        return str(local_path)


def get_kubeconfig_path() -> str:
    """Get kubeconfig path."""
    loader = KubeconfigLoader()
    return loader.load_kubeconfig()

