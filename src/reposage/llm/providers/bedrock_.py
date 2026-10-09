"""AWS Bedrock client provider placeholder."""

from reposage.llm.types import LLMRequest, LLMResponse


class BedrockProvider:
    """Invokes AWS Bedrock Foundation Models."""

    name: str = "bedrock"

    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name

    async def chat(self, req: LLMRequest) -> LLMResponse:
        """Call Bedrock InvokeModel API."""
        raise NotImplementedError("Bedrock provider requires boto3 AWS credentials")

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Call Bedrock Titan embeddings."""
        raise NotImplementedError("Bedrock embeddings require boto3 AWS credentials")
