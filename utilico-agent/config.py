import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_NAME: str = os.environ.get("DATABASE_NAME", "utilico_mock")

# LLM provider: "bedrock" (AWS) or "anthropic" (direct API)
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic").lower()

# Direct Anthropic API (used when LLM_PROVIDER=anthropic)
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_NAME: str = "claude-sonnet-4-20250514"

# AWS Bedrock (used when LLM_PROVIDER=bedrock). In ap-south-1 Claude must be
# invoked via an inference profile (the "apac.*" model IDs).
AWS_REGION: str = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID: str = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
BEDROCK_MODEL_ID: str = os.environ.get("BEDROCK_MODEL_ID", "apac.anthropic.claude-sonnet-4-20250514-v1:0")
