FROM python:3.11-slim
WORKDIR /app

# Install ami_tools first (relative path inside the build context)
COPY agents/tools /tmp/ami_tools
RUN pip install --no-cache-dir /tmp/ami_tools

COPY apps/dashboard-api/requirements.txt /app/requirements.txt
# Strip the editable line (handled above)
RUN sed -i '/ami\/tools/d; /-e .*ami_tools/d; /-e .*tools/d' /app/requirements.txt && \
    pip install --no-cache-dir -r /app/requirements.txt

# Include seed script + agent specs so the container can self-register in Foundry
COPY scripts/seed-foundry-agents.py /app/scripts/seed-foundry-agents.py
COPY agents /app/agents

COPY apps/dashboard-api/app /app/app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
