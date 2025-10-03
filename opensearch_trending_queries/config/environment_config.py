"""
Environment-specific configuration for the OpenSearch Trending Queries system
"""
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class EnvironmentConfig:
    """Configuration class for environment-specific settings"""
    
    def __init__(self, env_name: str):
        self.env_name = env_name
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration based on environment"""
        
        # Base configuration
        base_config = {
            "kinesis": {
                "shard_count": 1,
                "retention_hours": 24
            },
            "s3": {
                "lifecycle_transition_days": 30,
                "glacier_transition_days": 90
            },
            "glue": {
                "max_concurrent_runs": 1,
                "timeout_minutes": 60
            },
            "dynamodb": {
                "billing_mode": "PAY_PER_REQUEST",
                "ttl_days": 30
            },
            "lambda": {
                "timeout_seconds": 300,
                "memory_mb": 512
            },
            "step_functions": {
                "timeout_minutes": 120
            },
            "api_gateway": {
                "throttle_rate_limit": 1000,
                "throttle_burst_limit": 2000
            },
            "ml": {
                "cluster_count": 10,
                "max_iterations": 20
            },
            "bedrock": {
                "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                "max_retries": 3,
                "retry_delay": 2
            },
            "orchestration": {
                "schedule_hour": 2,
                "schedule_minute": 0,
                "timezone": "UTC"
            },
            "monitoring": {
                "alert_email": None  # Set to email address for alerts
            }
        }
        
        # Environment-specific overrides
        env_configs = {
            "dev": {
                "kinesis": {"shard_count": 1},
                "glue": {"max_concurrent_runs": 1},
                "lambda": {"memory_mb": 256}
            },
            "staging": {
                "kinesis": {"shard_count": 2},
                "glue": {"max_concurrent_runs": 2},
                "lambda": {"memory_mb": 512}
            },
            "prod": {
                "kinesis": {"shard_count": 5},
                "glue": {"max_concurrent_runs": 3},
                "lambda": {"memory_mb": 1024},
                "api_gateway": {
                    "throttle_rate_limit": 5000,
                    "throttle_burst_limit": 10000
                }
            }
        }
        
        # Merge configurations
        self.config = base_config.copy()
        if self.env_name in env_configs:
            self._deep_merge(self.config, env_configs[self.env_name])
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Deep merge override configuration into base configuration"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def get(self, service: str, key: str = None, default: Any = None) -> Any:
        """Get configuration value for a service"""
        if key is None:
            return self.config.get(service, {})
        return self.config.get(service, {}).get(key, default)
    
    @property
    def is_production(self) -> bool:
        """Check if this is a production environment"""
        return self.env_name == "prod"
    
    @property
    def resource_prefix(self) -> str:
        """Get resource naming prefix"""
        return f"opensearch-trending-{self.env_name}"