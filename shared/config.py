from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Backend webhook (fallback)
    BACKEND_WEBHOOK_URL: str = "http://localhost:8000/ingest/webhook/status"
    WEBHOOK_SECRET: str = "supersecretwebhookkey"

    # SQS
    SQS_QUEUE_URL: str = "http://localhost:4566/000000000000/ingestion-status"
    SQS_REGION: str = "us-east-1"
    SQS_ENDPOINT_URL: str = ""

    # S3
    S3_BUCKET_NAME: str = "agensus"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""

    # PostgreSQL (for direct Lambda DB access)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres_user"
    POSTGRES_PASSWORD: str = "postgres_password"
    POSTGRES_DB: str = "dms_db"

    # VoyageAI
    VOYAGEAI_API_KEY: str = ""
    VOYAGEAI_MODEL: str = "voyage-3"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "document_chunks"

    # OpenAI (for compakt)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"


settings = Settings()
