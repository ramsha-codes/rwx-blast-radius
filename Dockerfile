# The scorer builds this on linux/amd64 and runs it with no network. The
# digest is the image we labeled every commit in: its Python and SQLite
# decide which sqlglot tests run, so keep it if your image runs them.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
COPY selector.py selector_map.json.gz isprof_profile.json.gz tpcds_micro_profile.json.gz micro_check.py /app/
# Pinned sqlglot sources + test helpers + TPC-DS fixtures for the tpcds micro-check (no network; bytecode built here)
COPY pristine /app/pristine
RUN python -m compileall -q /app/pristine
CMD ["python", "/app/selector.py"]
