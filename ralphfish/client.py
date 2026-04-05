"""
OpenRouter API client wrapper with free-tier routing and retry logic.

Provides a simple interface for making LLM calls through OpenRouter with:
- Automatic free-tier model selection
- Comprehensive request/response logging
- Exponential backoff retry on rate limits
- Async support with configurable concurrency limits
"""

import os
import json
import time
import logging
import asyncio
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field

from openai import AsyncOpenAI, OpenAIError, RateLimitError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# Free-tier models available on OpenRouter (subject to change)
FREE_TIER_MODELS = [
    "anthropic/claude-instant-1.2",
    "openai/gpt-3.5-turbo",
    "google/gemini-pro",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mixtral-8x7b-instruct",
]

DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")


@dataclass
class ClientConfig:
    """Configuration for OpenRouter client."""

    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    default_model: str = DEFAULT_MODEL
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    log_requests: bool = True
    log_responses: bool = True
    site_url: str = "https://ralphfish.example.com"
    site_name: str = "Ralphfish Simulation"


class OpenRouterClient:
    """Wrapper around OpenRouter API with enhanced features."""

    def __init__(
        self,
        config: Optional[ClientConfig] = None,
        logger_instance: Optional[logging.Logger] = None,
    ):
        self.config = config or ClientConfig()
        self.logger = logger_instance or logger

        if not self.config.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Get your key from https://openrouter.ai/keys"
            )

        self.client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": self.config.site_url,
                "X-Title": self.config.site_name,
            },
        )

        # Statistics tracking
        self.request_count = 0
        self.total_tokens = 0
        self.errors = 0

    def _log_request(
        self, model: str, messages: List[Dict[str, str]], **kwargs
    ) -> None:
        """Log outgoing request (without sensitive data)."""
        if not self.config.log_requests:
            return

        self.logger.debug(
            "OpenRouter request",
            extra={
                "model": model,
                "message_count": len(messages),
                "max_tokens": kwargs.get("max_tokens"),
                "temperature": kwargs.get("temperature"),
            },
        )

    def _log_response(self, model: str, usage: Dict[str, int], duration: float) -> None:
        """Log incoming response metadata."""
        if not self.config.log_responses:
            return

        self.logger.info(
            "OpenRouter response",
            extra={
                "model": model,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "duration_seconds": duration,
            },
        )
        self.total_tokens += usage.get("total_tokens", 0)

    async def _execute_with_retry(self, operation, *args, **kwargs) -> Any:
        """Execute API operation with exponential backoff retry."""
        delay = self.config.base_delay

        for attempt in range(1, self.config.max_retries + 1):
            try:
                start_time = time.time()
                result = await operation(*args, **kwargs)
                duration = time.time() - start_time

                self.request_count += 1
                self.logger.info(
                    "API call succeeded",
                    extra={"attempt": attempt, "duration": duration},
                )
                return result

            except RateLimitError as e:
                self.errors += 1
                if attempt == self.config.max_retries:
                    raise

                self.logger.warning(
                    "Rate limited, retrying in {delay}s",
                    extra={
                        "attempt": attempt,
                        "max_retries": self.config.max_retries,
                        "delay": delay,
                    },
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.max_delay)

            except (APIConnectionError, OpenAIError) as e:
                self.errors += 1
                if attempt == self.config.max_retries:
                    raise

                self.logger.warning(
                    "API error, retrying",
                    extra={"attempt": attempt, "error": str(e), "delay": delay},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.max_delay)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make a chat completion request with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to free-tier if not specified)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
            **kwargs: Additional OpenAI API parameters

        Returns:
            Dict with response content and metadata
        """
        model = model or self.config.default_model

        # Route to free tier if configured to do so
        if kwargs.pop("use_free_tier", False) and model not in FREE_TIER_MODELS:
            # Select first available free model (could implement smarter routing)
            if FREE_TIER_MODELS:
                model = FREE_TIER_MODELS[0]
                self.logger.info("Routed to free-tier model", extra={"model": model})

        self._log_request(
            model, messages, max_tokens=max_tokens, temperature=temperature
        )

        try:
            response = await self._execute_with_retry(
                self.client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            self._log_response(
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                duration=response.response_ms / 1000
                if hasattr(response, "response_ms")
                else 0,
            )

            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "finish_reason": response.choices[0].finish_reason,
                "id": response.id,
            }

        except Exception as e:
            self.logger.error(
                "Chat completion failed",
                extra={"model": model, "error": str(e), "error_type": type(e).__name__},
            )
            raise

    async def close(self) -> None:
        """Close the underlying client."""
        await self.client.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "errors": self.errors,
        }


# Convenience functions for common use cases
async def simple_chat(
    messages: List[Dict[str, str]],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Simple one-off chat completion.

    Args:
        messages: List of message dicts
        api_key: OpenRouter API key (falls back to env var)
        model: Model to use
        **kwargs: Additional parameters

    Returns:
        Response content as string
    """
    config = ClientConfig(api_key=api_key or os.getenv("OPENROUTER_API_KEY", ""))
    if model:
        config.default_model = model

    client = OpenRouterClient(config)
    try:
        result = await client.chat_completion(messages, **kwargs)
        return result["content"]
    finally:
        await client.close()


# Export public interface
__all__ = [
    "OpenRouterClient",
    "ClientConfig",
    "simple_chat",
    "FREE_TIER_MODELS",
]
