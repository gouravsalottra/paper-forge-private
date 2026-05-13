FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn aiofiles python-multipart openai python-dotenv pandas yfinance
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
