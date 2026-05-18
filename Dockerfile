FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

WORKDIR /app

RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn.list.save \
    && apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn python-multipart aiofiles

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
