# EpisAlpha research worker image (M3-T04, amendment A12).
#
# Built by episalpha.runtime.sandbox.build_image() from a minimal context: the pinned Hermes
# source (git archive of c1488ac947c9bc33fd65ec464548dc9d8edd6122, version 0.21.3), the stage
# worker and the forwarder. The repository, .env and the canonical data never enter the context.
# Hermes' own dependency lock (uv.lock) is installed exactly; of its optional extras only `mcp`
# is installed, which the worker needs to reach the host tool server.
FROM python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv==0.11.6

COPY hermes-agent /opt/hermes
RUN cd /opt/hermes \
    && uv sync --frozen --no-dev --extra mcp --python /usr/local/bin/python3.12 \
    && rm -rf /root/.cache

COPY hermes_stage.py forwarder.py /opt/episalpha/

RUN useradd --uid 10001 --no-create-home --home-dir /home/worker --shell /usr/sbin/nologin worker
USER 10001:10001
WORKDIR /opt/hermes
ENTRYPOINT []
CMD ["/opt/hermes/.venv/bin/python", "/opt/episalpha/hermes_stage.py"]
