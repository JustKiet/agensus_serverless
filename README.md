# aws/ — Ingestion Pipeline

Step Functions-orchestrated ETL pipeline: Extract → Transform → Load.

## Structure

```
aws/
├── workers/
│   └── extract/
│       ├── main.py            # Long-running worker (polls SFN activity)
│       ├── Dockerfile         # Fast image — inherits from base
│       └── Dockerfile.base    # Heavy base image (Docling + HF models, build once)
├── lambdas/
│   ├── transform/
│   │   ├── main.py            # Chunking Lambda
│   │   └── Dockerfile
│   └── load/
│       ├── main.py            # Vectorize + store Lambda
│       └── Dockerfile
├── shared/                    # Shared package (config, db, sqs, vectorizer, chunker)
│   ├── config.py
│   ├── db.py
│   ├── sqs.py
│   ├── vectorizer.py
│   ├── chunker.py
│   ├── callbacks.py
│   └── pyproject.toml
├── statemachines/
│   └── ingestion_pipeline.asl.json   # Step Functions ASL definition
└── pyproject.toml             # UV workspace root
```

## Pipeline

```
Step Functions Execution
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  Extract  (Activity Task)                                    │
│  Resource: arn:aws:states:...:activity:extract-worker        │
│                                                              │
│  Worker polls GetActivityTask → processes → SendTaskSuccess  │
└─────────────────────────────┬───────────────────────────────┘
                              │  {bucket, key, blob_name, job_id,
                              │   extracted_text, summary_blob_name}
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Transform  (Lambda: ingestion-transform)                    │
│  - Hash-dedup document                                       │
│  - LangChain markdown chunking                               │
│  - Create document record in Postgres                        │
└─────────────────────────────┬───────────────────────────────┘
                              │  {chunks, document_id, ...}
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Load  (Lambda: ingestion-load)                              │
│  - VoyageAI batch vectorization                              │
│  - Qdrant upsert                                             │
│  - Postgres chunk storage                                    │
│  - Compakt/OpenAI summary generation                         │
└─────────────────────────────────────────────────────────────┘
```

SQS status events are pushed at each stage transition (`EXTRACTING → EXTRACTED → CHUNKING → CHUNKED → VECTORIZING → VECTORIZED → SUMMARIZING → COMPLETED`). The backend consumes these to push real-time WebSocket updates to the client.

## Tech Stack

| Component | Technology |
|---|---|
| Orchestration | AWS Step Functions (ASL) |
| Extract runtime | Python 3.13, Docker container (long-lived) |
| Lambda runtime | `public.ecr.aws/lambda/python:3.13` |
| Document parsing | [Docling](https://github.com/DS4SD/docling) — OCR + layout analysis via PyTorch |
| MIME detection | python-magic (libmagic) |
| Text chunking | LangChain text splitters |
| Embeddings | VoyageAI (`voyage-3`) |
| Vector store | Qdrant |
| Summarization | [Compakt](https://github.com/JustKiet/compakt) + OpenAI (`gpt-4o-mini`) |
| Messaging | AWS SQS |
| Blob storage | AWS S3 / MinIO |
| Database | PostgreSQL (psycopg2, synchronous) |
| Package manager | UV workspace |

## Extract Worker — Why Not Lambda?

Docling loads PyTorch-based OCR and layout models at startup (~1–2 minutes, ~2 GB). As a Lambda this causes cold-start hangs and risks the 15-minute timeout on large documents.

The worker runs as a **persistent Docker container** that:
1. Loads models once at startup
2. Long-polls `sfn:GetActivityTask` (60s timeout per poll)
3. Processes each task and calls `sfn:SendTaskSuccess`
4. Loops — models stay warm across all subsequent jobs

To scale horizontally, run multiple worker containers — Step Functions distributes tasks across all pollers (each `GetActivityTask` response is exclusive).

### Docker image split

| Image | When to rebuild | Contents |
|---|---|---|
| `agensus-extract-base` | Deps or HF models change | apt libs, uv deps, ~1 GB of Docling HF models baked in |
| `agensus-extract-worker` | Code changes (`main.py`, `shared/`) | Inherits base, copies worker code only |

Rebuild base: `make deploy-base` (~30 min first time, cached on rebuilds).  
Normal deploy: `make deploy` (seconds — only rebuilds the worker + Lambda images).

## Shared Package

`shared/` is installed into all Lambda images and the worker at build time. It provides:

| Module | Purpose |
|---|---|
| `config.py` | `pydantic-settings` config (S3, SQS, Postgres, VoyageAI, Qdrant, OpenAI) |
| `db.py` | Synchronous Postgres helpers (`create_document`, `update_ingestion_status`, `store_chunks`) |
| `sqs.py` | `push_status_event()` with HTTP webhook fallback |
| `vectorizer.py` | `SyncVoyageAIVectorizer.batch_vectorize()` |
| `chunker.py` | `MarkdownChunker.chunk()` |
| `callbacks.py` | `notify_backend()` HTTP webhook (fallback when SQS unavailable) |

## Local Development

### Prerequisites
- Docker
- LocalStack Hobby (`lstk`)
- AWS CLI
- `.env` with `VOYAGEAI_API_KEY` and `OPENAI_API_KEY`

### Deploy to LocalStack

```bash
# From repo root — first time (builds base image + bakes in HF models, ~30 min)
make deploy-base

# Subsequent deploys (fast — only rebuilds worker + Lambda images)
make deploy
```

The deploy script (`infrastructure/deploy-lambdas.sh`):
1. Builds `agensus-extract-base` (if `--build-base` or missing) and `agensus-extract-worker`
2. Builds `agensus-transform` and `agensus-load` Lambda images
3. Ensures S3 bucket and SQS queue exist
4. Registers the `extract-worker` SFN activity, captures its ARN
5. Starts the extract worker container (`--network host`, `localhost` endpoints)
6. Creates or updates Transform + Load Lambda functions with environment variables
7. Deploys the Step Functions state machine (substitutes `${ExtractActivityArn}`, `${TransformFunctionArn}`, `${LoadFunctionArn}` in the ASL)

### Inspect

```bash
make logs-worker        # extract worker polling loop
make logs-transform     # transform Lambda (CloudWatch via LocalStack)
make logs-load          # load Lambda (CloudWatch via LocalStack)
make status             # Lambda functions, SFN activities, worker container status
```

### Networking Notes

| Container | Reaches LocalStack via |
|---|---|
| Extract worker | `localhost:4566` (`--network host`) |
| Transform / Load Lambda | `AWS_ENDPOINT_URL` auto-injected by LocalStack |

Lambda containers cannot use `127.0.0.1` on the host. LocalStack injects its own reachable `AWS_ENDPOINT_URL` automatically — so `S3_ENDPOINT_URL` and `SQS_ENDPOINT_URL` are intentionally omitted from Lambda env vars. Postgres and Qdrant are reached at `172.17.0.1` (Docker bridge gateway).

## State Machine Input

```json
{
  "bucket": "agensus",
  "key": "users/{user_id}/{uuid}_{filename}.pdf",
  "blob_name": "users/{user_id}/{uuid}_{filename}.pdf",
  "job_id": "some-uuid"
}
```
