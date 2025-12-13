# app/model_invoker.py
import time
import os
import logging
from typing import Optional, Dict, Any

from app import bedrock_client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_RETRIES = int(os.environ.get("MODEL_INVOKER_RETRIES", "3"))
DEFAULT_BACKOFF = float(os.environ.get("MODEL_INVOKER_BACKOFF", "1.2"))
DEFAULT_TIMEOUT = int(os.environ.get("MODEL_INVOKER_TIMEOUT", "30"))

class ModelInvoker:
    def __init__(self, text_model_id: Optional[str] = None, embed_model_id: Optional[str] = None):
        self.text_model_id = text_model_id or os.environ.get("BEDROCK_MODEL_SUMMARY")
        self.embed_model_id = embed_model_id or os.environ.get("BEDROCK_MODEL_EMBED")

    def _retry_loop(self, fn, *args, retries=DEFAULT_RETRIES, backoff=DEFAULT_BACKOFF, **kwargs):
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                attempt += 1
                logger.warning("ModelInvoker attempt %s failed: %s", attempt, str(e))
                if attempt >= retries:
                    logger.error("ModelInvoker exhausted retries (%s). Raising.", retries)
                    raise
                wait = backoff * (2 ** (attempt - 1))
                logger.info("Retrying after %.2f seconds...", wait)
                time.sleep(wait)

    def generate(self, prompt: str, model_id: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        """
        Returns a dict: {"success": bool, "text": "<model response>", "raw": <raw-response>}
        """
        if not getattr(bedrock_client, "ENABLE_BEDROCK", False):
            # safe fallback - echo prompt for debugging
            return {"success": False, "text": prompt, "raw": None, "note": "bedrock disabled"}

        mid = model_id or self.text_model_id
        if not mid:
            raise ValueError("No model id provided for generate()")

        def call():
            return bedrock_client.invoke_model(mid, {"input": prompt}, timeout_seconds=timeout)

        raw = self._retry_loop(call)
        # Normalize `raw` -> text
        text = None
        if isinstance(raw, dict):
            # handle common fields
            text = raw.get("outputText") or raw.get("text") or raw.get("generated_text") or raw.get("body") or str(raw)
        else:
            text = str(raw)
        return {"success": True, "text": text, "raw": raw}

    def embed(self, text: str, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns {"success": bool, "embedding": [...], "raw": <raw>}
        """
        if not getattr(bedrock_client, "ENABLE_BEDROCK", False):
            return {"success": False, "embedding": None, "note": "bedrock disabled"}

        mid = model_id or self.embed_model_id
        if not mid:
            raise ValueError("No model id provided for embed()")

        def call():
            # adapt signature if your bedrock_client.create_embedding requires different params
            return bedrock_client.create_embedding(text, model=mid) if "model" in bedrock_client.create_embedding.__code__.co_varnames else bedrock_client.create_embedding(text)

        raw = self._retry_loop(call)
        embedding = None
        if isinstance(raw, dict):
            embedding = raw.get("embedding") or raw.get("embeddings") or raw.get("data") or raw.get("vector") or raw
        else:
            embedding = raw
        return {"success": True, "embedding": embedding, "raw": raw}
