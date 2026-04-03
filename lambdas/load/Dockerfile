FROM public.ecr.aws/lambda/python:3.13

# git needed for compakt (installed from github)
RUN dnf install -y git && dnf clean all

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install shared package
COPY shared/ /tmp/shared/
RUN uv pip install --system /tmp/shared/ --default-index https://pypi.org/simple

# Install compakt from git explicitly (uv sources not available outside workspace)
RUN uv pip install --system "compakt @ git+https://github.com/JustKiet/compakt.git" --default-index https://pypi.org/simple

# Install load lambda deps (shared + compakt already installed above)
RUN uv pip install --system \
    "aws-lambda-powertools>=3.26.0" \
    "aws-lambda-typing>=2.20.0" \
    --default-index https://pypi.org/simple

# Copy handler code
COPY lambdas/load/main.py ${LAMBDA_TASK_ROOT}/main.py

CMD ["main.main"]
