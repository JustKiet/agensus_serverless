FROM public.ecr.aws/lambda/python:3.13

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install shared package
COPY shared/ /tmp/shared/
RUN uv pip install --system /tmp/shared/ --default-index https://pypi.org/simple

# Install transform lambda deps (shared already installed above)
RUN uv pip install --system \
    "aws-lambda-powertools>=3.26.0" \
    "aws-lambda-typing>=2.20.0" \
    --default-index https://pypi.org/simple

# Copy handler code
COPY lambdas/transform/main.py ${LAMBDA_TASK_ROOT}/main.py

CMD ["main.main"]
