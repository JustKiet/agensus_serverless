"""Sync VoyageAI vectorizer for Lambda functions."""

from typing import Sequence

import voyageai
from shared.config import settings

VectorLike = list[float] | list[int]  # Qdrant accepts both float and int vectors


class SyncVoyageAIVectorizer:
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.client = voyageai.Client(api_key=api_key or settings.VOYAGEAI_API_KEY)
        self.model_name = model_name or settings.VOYAGEAI_MODEL

    def vectorize(self, text: str, input_type: str = "document") -> VectorLike:
        response = self.client.embed(
            texts=[text],
            model=self.model_name,
            input_type=input_type,
        )
        return response.embeddings[0]

    def batch_vectorize(
        self, texts: list[str], input_type: str = "document"
    ) -> Sequence[VectorLike]:
        response = self.client.embed(
            texts=texts,
            model=self.model_name,
            input_type=input_type,
        )
        return response.embeddings
