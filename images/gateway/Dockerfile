# Omarchy Local AI gateway: one endpoint for OpenAI chat, Anthropic Messages,
# and OpenAI Responses in front of any engine that speaks chat completions.
# Standard-library Python, no packages, runs as an unprivileged user.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

RUN useradd --system --uid 10001 --create-home gateway
COPY gateway.py /app/gateway.py
USER gateway
ENV GATEWAY_PORT=12434 UPSTREAM=http://engine:8000 PYTHONUNBUFFERED=1
EXPOSE 12434
ENTRYPOINT ["python3", "/app/gateway.py"]
