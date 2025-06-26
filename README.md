## k8s-mcp (AI + Model Control Plane)

A FastAPI-based microservice that provides natural language querying and filtering of Kubernetes resources. It integrates with Supabase for user context and Google Gemini for language processing, enabling real-time interactions with multi-cluster environments.

## Quick Start

Prerequisites:
- Python 3.8+
- A running Kubernetes cluster
- Supabase project (with URL and service key)
- Google Gemini API key
- AWS credentials (for S3 kubeconfig access)

1. Copy and fill environment variables

    ```bash
    cp .env.example .env
    ```

    Then open `.env` in an editor, update values as needed, then export variables by pasting its contents into your terminal

2. Create and Activate a Virtual Environment

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # for Unix/macOS
   # .venv\Scripts\activate    # for Windows
   ```

3. Install Dependencies

   ```bash
   pip install -r requirements.txt
   ```

4. Run the Server

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

API will be available at [http://localhost:8000](http://localhost:8000)

## Example API Usage

1. Filter Kubernetes Resources

   ```bash
   curl -X POST http://localhost:8000/api/v1/filter/query \
   -H "Content-Type: application/json" \
   -d '{"query": "Show me pods created yesterday"}'
   ```

2. Ask an Agent Prompt

   ```bash
   curl -X POST "http://localhost:8000/api/v1/agent/query?cluster_id=your-cluster-id" \
   -H "Content-Type: application/json" \
   -d '{"prompt": "List all running pods"}'
   ```

## Features

- Natural Language Querying: Ask questions about your Kubernetes resources in plain English
- Resource Filtering: Filter resources by type, date range, and other attributes
- Multi-cluster Support: Connect to and query multiple Kubernetes clusters
- RESTful API: Well-documented endpoints for programmatic access
- Real-time Responses: Get immediate feedback on your cluster's state

## API Documentation

* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Project Structure

```
.
├── handlers/               # Request handlers
│   ├── agent_handler.py
│   └── filter_handler.py
├── models/                 # Pydantic schemas
│   └── model.py
├── services/               # Core business logic
│   └── query_parser.py
├── utils/                  # Utility functions
│   └── utils.py
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
└── README.md               # This file
```
