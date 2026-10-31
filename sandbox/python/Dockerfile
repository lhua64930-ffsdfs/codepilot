FROM python:3.12-slim
RUN pip install --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple pytest==9.2.0
COPY runner.py /opt/codepilot/runner.py
USER 10001:10001
WORKDIR /workspace
