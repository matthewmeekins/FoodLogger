# Food Logging System

A personal food logging system that uses voice/text input and AI parsing to structure food entries.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create `.env` file with your OpenAI API key:
   ```
   OPENAI_API_KEY=your-actual-key-here
   ```

3. Run the server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Usage

### Test with curl
```bash
curl -X POST http://localhost:8000/log \
  -H "Content-Type: text/plain" \
  -d "had oatmeal with banana for breakfast and a chicken sandwich for lunch"
```

### View today's entries
```bash
curl http://localhost:8000/log/today
```

### View 7-day summary
```bash
curl http://localhost:8000/log/summary
```
