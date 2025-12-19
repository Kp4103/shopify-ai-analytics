# AI-Powered Shopify Analytics App

A mini AI-powered analytics application that connects to Shopify stores and allows users to ask natural language questions about their store data. The system translates questions into ShopifyQL queries, fetches data from Shopify, and returns answers in business-friendly language.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Client/User   │────▶│   Rails API      │────▶│  Python AI      │
│                 │◀────│   (Gateway)      │◀────│  Service        │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                │                         │
                                │                         ▼
                                │                  ┌─────────────────┐
                                │                  │  Google Gemini  │
                                │                  │  (LLM)          │
                                │                  └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  Shopify API     │
                        │  (GraphQL +      │
                        │   ShopifyQL)     │
                        └──────────────────┘
```

### Components

1. **Rails API Gateway** (`rails-api/`)
   - Handles Shopify OAuth authentication
   - Exposes REST API endpoints
   - Manages store credentials securely
   - Routes questions to Python AI service

2. **Python AI Service** (`python-ai-service/`)
   - FastAPI-based microservice
   - LLM-powered agent using Google Gemini
   - Generates ShopifyQL queries from natural language
   - Formats responses in business-friendly language

## Agent Workflow

The AI agent follows a structured workflow to process questions:

```
User Question
     │
     ▼
┌─────────────────┐
│ 1. Intent       │  Classify: inventory | sales | customers | orders
│    Classification│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Query        │  Determine tables, fields, time ranges
│    Planning     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. ShopifyQL    │  Generate syntactically correct query
│    Generation   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. Validation   │  Check syntax, validate fields
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Execution    │  Call Shopify API, handle errors
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. Response     │  Convert to business-friendly language
│    Formatting   │
└─────────────────┘
```

## Features

- **Natural Language Interface**: Ask questions in plain English
- **Intent Classification**: Automatically detects question type (sales, inventory, customers, orders)
- **ShopifyQL Generation**: Translates questions into valid ShopifyQL queries
- **Query Validation**: Validates queries before execution
- **Response Formatting**: Converts raw data into actionable insights
- **Caching**: Redis-based caching for improved performance
- **Conversation Memory**: Supports follow-up questions with context
- **Secure Token Storage**: Encrypted access token storage
- **Smart Fallback System**: Automatic GraphQL fallback for dev stores

## ShopifyQL to GraphQL Fallback

The system uses ShopifyQL as the primary query method (as required by the assignment), with automatic GraphQL fallback for development stores that don't support ShopifyQL.

### How It Works

```
User Question
     │
     ▼
Generate ShopifyQL Query
     │
     ▼
┌─────────────────────┐
│ Try ShopifyQL First │ ◄── Primary method (assignment requirement)
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │ Success?  │
     └─────┬─────┘
           │
    Yes ───┴─── No (ShopifyQL unavailable)
     │              │
     ▼              ▼
  Return      ┌─────────────────┐
  Results     │ GraphQL Fallback│ ◄── Automatic fallback for dev stores
              └────────┬────────┘
                       │
                       ▼
                 Return Results
                 (with fallback_used: true)
```

### Response Indicators

The API response includes metadata about which query method was used:

```json
{
  "answer": "Here are your 6 products...",
  "data_source": "graphql_fallback",
  "fallback_used": true,
  "query_used": "FROM inventory SHOW product_title..."
}
```

- `data_source`: Either `"shopifyql"` or `"graphql_fallback"`
- `fallback_used`: `true` if GraphQL fallback was used
- `query_used`: The original ShopifyQL query that was attempted

### Why Fallback is Needed

ShopifyQL analytics queries are only available on **Shopify Plus** stores. Development stores and standard Shopify plans don't have access to ShopifyQL. The fallback ensures the app works across all store types while still demonstrating ShopifyQL query generation.

## Prerequisites

- **Ruby 3.2+** and **Rails 7.1+**
- **Python 3.10+**
- **PostgreSQL 14+**
- **Redis** (optional, for caching)
- **Shopify Partner Account** with a development store
- **Google Cloud API Key** for Gemini

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd shopify-ai-analytics
```

### 2. Set Up the Python AI Service

```bash
cd python-ai-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY
```

### 3. Set Up the Rails API

```bash
cd rails-api

# Install dependencies
bundle install

# Configure environment
cp .env.example .env
# Edit .env with your Shopify credentials

# Set up database
rails db:create
rails db:migrate
```

### 4. Create Shopify App

1. Go to [Shopify Partners](https://partners.shopify.com/)
2. Create a new app
3. Configure the app URLs:
   - App URL: `http://localhost:3000`
   - Allowed redirection URLs: `http://localhost:3000/auth/shopify/callback`
4. Copy the API Key and Secret to your `.env` file
5. Required scopes: `read_orders`, `read_products`, `read_inventory`, `read_customers`

### 5. Start the Services

**Terminal 1 - Python AI Service:**
```bash
cd python-ai-service
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - Rails API:**
```bash
cd rails-api
rails server -p 3000
```

## API Usage

### 1. Connect a Store (OAuth)

```bash
# Redirect user to:
GET http://localhost:3000/auth/shopify?shop=your-store.myshopify.com
```

### 2. Ask a Question

```bash
curl -X POST http://localhost:3000/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "your-store.myshopify.com",
    "question": "What were my top 5 selling products last week?"
  }'
```

**Response:**
```json
{
  "answer": "Your top 5 selling products last week were: 1) Blue T-Shirt ($1,234.56, 45 units), 2) Black Jeans ($987.65, 32 units), 3) White Sneakers ($876.54, 28 units), 4) Red Cap ($543.21, 25 units), 5) Green Hoodie ($432.10, 20 units).",
  "confidence": "high",
  "query_used": "FROM sales SHOW product_title, sum(net_sales) AS total_sales...",
  "conversation_id": "abc-123",
  "timestamp": "2024-12-18T10:30:00Z"
}
```

### 3. Follow-up Questions

```bash
curl -X POST http://localhost:3000/api/v1/questions \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": "your-store.myshopify.com",
    "question": "What about last month?",
    "conversation_id": "abc-123"
  }'
```

## Example Questions

| Question | Intent |
|----------|--------|
| "What were my top 5 selling products last week?" | sales |
| "Which products are likely to go out of stock in 7 days?" | inventory |
| "How much inventory should I reorder based on last 30 days sales?" | inventory |
| "Which customers placed repeat orders in the last 90 days?" | customers |
| "What's my total revenue this month?" | sales |

## API Endpoints

### Rails API (Port 3000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/auth/shopify` | Start OAuth flow |
| GET | `/auth/shopify/callback` | OAuth callback |
| POST | `/api/v1/questions` | Ask a question |
| GET | `/api/v1/stores` | List connected stores |
| GET | `/api/v1/stores/:id` | Get store details |
| GET | `/api/v1/stores/:id/test_connection` | Test Shopify connection |

### Python AI Service (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/health` | Detailed health check |
| POST | `/api/v1/analyze` | Analyze a question |
| POST | `/api/v1/validate-query` | Validate ShopifyQL |

## Project Structure

```
shopify-ai-analytics/
├── rails-api/
│   ├── app/
│   │   ├── controllers/
│   │   │   ├── api/v1/
│   │   │   │   ├── questions_controller.rb
│   │   │   │   └── stores_controller.rb
│   │   │   ├── auth_controller.rb
│   │   │   └── health_controller.rb
│   │   ├── models/
│   │   │   ├── store.rb
│   │   │   └── request_log.rb
│   │   └── services/
│   │       ├── ai_service_client.rb
│   │       └── shopify_api_service.rb
│   ├── config/
│   │   ├── routes.rb
│   │   └── database.yml
│   └── db/migrate/
│
├── python-ai-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── agent/
│   │   │   ├── orchestrator.py
│   │   │   ├── intent_classifier.py
│   │   │   ├── query_generator.py
│   │   │   ├── query_validator.py
│   │   │   └── response_formatter.py
│   │   ├── llm/
│   │   │   └── gemini_client.py
│   │   ├── shopify/
│   │   │   └── client.py
│   │   ├── cache/
│   │   │   └── redis_cache.py
│   │   └── memory/
│   │       └── conversation_store.py
│   └── requirements.txt
│
└── README.md
```

## Configuration

### Environment Variables

**Rails API (.env):**
```env
SHOPIFY_API_KEY=xxx
SHOPIFY_API_SECRET=xxx
PYTHON_AI_SERVICE_URL=http://localhost:8000
DATABASE_URL=postgres://...
ENCRYPTION_KEY=32-character-key
```

**Python AI Service (.env):**
```env
GOOGLE_API_KEY=xxx
REDIS_URL=redis://localhost:6379
CACHE_TTL_SECONDS=300
```

## Error Handling

The system handles various error scenarios:

- **Empty Results**: Returns helpful message about no matching data
- **Ambiguous Questions**: Asks for clarification
- **Invalid Store**: Returns authentication error
- **API Rate Limits**: Implements retry with backoff
- **LLM Failures**: Falls back to basic responses

## Testing

### Rails API
```bash
cd rails-api
bundle exec rspec
```

### Python AI Service
```bash
cd python-ai-service
pytest
```

## Bonus Features Implemented

- [x] Caching Shopify responses (Redis)
- [x] Conversation memory for follow-up questions
- [x] Query validation layer for ShopifyQL
- [x] Request logging for debugging
- [x] Retry & fallback logic in agent

## Security Considerations

- Access tokens are encrypted at rest using AES-256-GCM
- OAuth flow includes HMAC verification and CSRF protection
- API endpoints require store authentication
- Environment variables for sensitive configuration

## License

MIT License
