FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
COPY requirements.lock /req.lock
RUN pip install -q --no-cache-dir -r /req.lock coverage \
 && python -c "import site;print(site.getsitepackages()[0])" > /sp.txt \
 && echo "import coverage; coverage.process_startup()" > "$(cat /sp.txt)/zz_cov.pth"
