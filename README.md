# Kubernetes Dashboard API

A FastAPI-based service that provides natural language querying and filtering of Kubernetes resources. This service integrates with Kubernetes clusters and offers both a natural language interface and structured API endpoints.

## Features

- **Natural Language Querying**: Ask questions about your Kubernetes resources in plain English
- **Resource Filtering**: Filter resources by type, date range, and other attributes
- **Multi-cluster Support**: Connect to and query multiple Kubernetes clusters
- **RESTful API**: Well-documented endpoints for programmatic access
- **Real-time Responses**: Get immediate feedback on your cluster's state

## Prerequisites

- Python 3.8+
- Kubernetes cluster access
- Google Gemini API key (for natural language processing)
- AWS credentials (if using S3 for kubeconfig storage)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/kubernetes-dashboard-api.git
   cd kubernetes-dashboard-api
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Configuration

Create a `.env` file with the following variables:

```env
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# AWS S3 Configuration (if using S3 for kubeconfig)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=your_bucket_name
S3_ENDPOINT=your_s3_endpoint
REGION=your_aws_region

# Kubernetes Configuration
KUBECONFIG_PATH=/path/to/your/kubeconfig
```

## Usage

### Starting the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

Once the server is running, you can access:
- Interactive API docs: `http://localhost:8000/docs`
- Alternative API docs: `http://localhost:8000/redoc`

### Example Requests

#### 1. Filter Resources

```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/filter/query' \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show me pods created yesterday"}'
```

#### 2. Agent Query

```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/agent/query?cluster_id=your-cluster-id' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "List all running pods"}'
```

## API Endpoints

### Filter Endpoints
- `POST /api/v1/filter/query` - Query resources using natural language

### Agent Endpoints
- `POST /api/v1/agent/query` - Execute agent-based queries

## Development

### Project Structure

```
.
├── handlers/               # Request handlers
│   ├── __init__.py
│   ├── agent_handler.py    # Agent query handling
│   └── filter_handler.py   # Filter query handling
├── models/                 # Pydantic models
│   └── model.py
├── services/               # Business logic
│   ├── __init__.py
│   └── query_parser.py     # Query parsing logic
├── utils/                  # Utility functions
│   ├── __init__.py
│   └── utils.py            # Helper functions
├── main.py                 # Application entry point
├── requirements.txt        # Project dependencies
└── README.md              # This file
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Support

For support, please open an issue in the GitHub repository.
 python3 gemini.py