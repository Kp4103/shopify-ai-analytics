"""
Query Generator - Generates ShopifyQL queries based on user intent

ShopifyQL is Shopify's query language for analytics. This module generates
syntactically correct queries based on the classified intent and entities.

Key ShopifyQL tables:
- sales: Order and revenue data
- products: Product information
- inventory: Stock levels by location
"""
import json
from typing import Dict, Any, List, Optional
import structlog

from app.llm.gemini_client import GeminiClient

logger = structlog.get_logger()

SHOPIFYQL_SCHEMA = """
ShopifyQL Schema Reference:

TABLES:
1. sales - Order and transaction data
   Fields: order_id, product_id, product_title, product_type, variant_id, variant_title,
           billing_city, billing_country, billing_region, shipping_city, shipping_country,
           net_sales, gross_sales, discounts, returns, taxes, total_sales,
           net_quantity, ordered_quantity, returned_quantity,
           day, hour, month, week, year

2. products - Product catalog
   Fields: product_id, product_title, product_type, vendor, product_tag

3. inventory - Current stock levels
   Fields: product_id, product_title, variant_id, variant_title,
           quantity_available, incoming_quantity, committed_quantity,
           location_id, location_name

SYNTAX:
- FROM <table>
- SHOW <field1>, <field2>, aggregate_function(field) AS alias
- WHERE <conditions>
- GROUP BY <field>
- ORDER BY <field> ASC|DESC
- SINCE <date> UNTIL <date>  (for time-based queries)
- LIMIT <number>

TIME EXPRESSIONS:
- SINCE -7d UNTIL today (last 7 days)
- SINCE -30d UNTIL today (last 30 days)
- SINCE -1m UNTIL today (last month)
- SINCE -1y UNTIL today (last year)

AGGREGATE FUNCTIONS:
- sum(field)
- count(field)
- avg(field)
- min(field)
- max(field)
"""

QUERY_GENERATION_PROMPT = """You are a ShopifyQL expert. Generate a ShopifyQL query for the given question.

{schema}

User Question: {question}
Classified Intent: {intent}
Extracted Entities: {entities}

{conversation_context}

Generate a ShopifyQL query that answers the question. Follow these rules:
1. Use the correct table based on intent (sales for revenue/orders, inventory for stock)
2. Include appropriate time ranges using SINCE/UNTIL
3. Use GROUP BY for aggregations
4. Use ORDER BY and LIMIT for "top N" queries
5. Ensure all field names are valid

Respond in JSON format:
{{
    "query": "the ShopifyQL query",
    "explanation": "brief explanation of what the query does",
    "fields_used": ["list", "of", "fields"],
    "table": "main table used"
}}
"""

REGENERATE_PROMPT = """The following ShopifyQL query had validation errors:

Query: {original_query}
Errors: {errors}

Please fix the query to address these errors. The original question was:
"{question}"

Intent: {intent}

{schema}

Respond in JSON format:
{{
    "query": "the corrected ShopifyQL query",
    "explanation": "what was fixed"
}}
"""


class QueryGenerator:
    """Generates ShopifyQL queries based on user intent"""

    def __init__(self):
        self.llm = GeminiClient()

    async def generate(
        self,
        question: str,
        intent: str,
        entities: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Generate a ShopifyQL query for the given question.

        Args:
            question: The user's question
            intent: Classified intent (inventory, sales, customers, orders)
            entities: Extracted entities (time_period, product_name, etc.)
            conversation_history: Previous conversation for context

        Returns:
            Dictionary with generated query and metadata
        """
        # Build conversation context if available
        context = ""
        if conversation_history:
            context = "Previous queries in this conversation:\n"
            for turn in conversation_history[-2:]:
                if turn.get("query"):
                    context += f"- {turn['query']}\n"

        prompt = QUERY_GENERATION_PROMPT.format(
            schema=SHOPIFYQL_SCHEMA,
            question=question,
            intent=intent,
            entities=json.dumps(entities),
            conversation_context=context
        )

        try:
            response = await self.llm.generate(prompt)
            result = self._parse_response(response)

            logger.info(
                "query_generated",
                table=result.get("table"),
                query_length=len(result.get("query", ""))
            )

            return result

        except Exception as e:
            logger.error("query_generation_error", error=str(e))
            # Return a fallback query
            return self._generate_fallback_query(intent, entities)

    async def regenerate_with_errors(
        self,
        original_query: str,
        errors: List[str],
        question: str,
        intent: str
    ) -> Dict[str, Any]:
        """
        Regenerate a query after validation errors.

        Args:
            original_query: The query that failed validation
            errors: List of validation errors
            question: Original user question
            intent: Classified intent

        Returns:
            Dictionary with corrected query
        """
        prompt = REGENERATE_PROMPT.format(
            original_query=original_query,
            errors=", ".join(errors),
            question=question,
            intent=intent,
            schema=SHOPIFYQL_SCHEMA
        )

        try:
            response = await self.llm.generate(prompt)
            result = self._parse_response(response)

            logger.info("query_regenerated", had_errors=len(errors))

            return result

        except Exception as e:
            logger.error("query_regeneration_error", error=str(e))
            return {"query": original_query, "explanation": "Could not regenerate"}

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM response into structured data"""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response.strip())

            if "query" not in result:
                raise ValueError("No query in response")

            return result

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("json_parse_error", error=str(e))
            # Try to extract query directly from response
            if "FROM" in response:
                # Find the query in the response
                lines = response.split("\n")
                query_lines = []
                in_query = False
                for line in lines:
                    if "FROM" in line:
                        in_query = True
                    if in_query:
                        query_lines.append(line)
                        if "LIMIT" in line or (not line.strip() and query_lines):
                            break

                return {
                    "query": " ".join(query_lines).strip(),
                    "explanation": "Extracted from response"
                }

            return {"query": "", "explanation": "Failed to parse response"}

    def _generate_fallback_query(
        self,
        intent: str,
        entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a fallback query based on intent"""
        time_period = entities.get("time_period", "last 7 days")
        limit = entities.get("limit", 10)

        # Convert time period to ShopifyQL format
        time_clause = self._parse_time_period(time_period)

        fallback_queries = {
            "sales": f"""
                FROM sales
                SHOW product_title, sum(net_sales) AS total_sales, sum(net_quantity) AS units_sold
                {time_clause}
                GROUP BY product_title
                ORDER BY total_sales DESC
                LIMIT {limit}
            """,
            "inventory": """
                FROM inventory
                SHOW product_title, sum(quantity_available) AS stock
                GROUP BY product_title
                ORDER BY stock ASC
                LIMIT 10
            """,
            "customers": f"""
                FROM sales
                SHOW billing_city, count(order_id) AS order_count
                {time_clause}
                GROUP BY billing_city
                ORDER BY order_count DESC
                LIMIT {limit}
            """,
            "orders": f"""
                FROM sales
                SHOW day, count(order_id) AS orders, sum(net_sales) AS revenue
                {time_clause}
                GROUP BY day
                ORDER BY day DESC
            """
        }

        query = fallback_queries.get(intent, fallback_queries["sales"])

        return {
            "query": " ".join(query.split()),  # Normalize whitespace
            "explanation": "Fallback query generated",
            "table": "sales" if intent in ["sales", "customers", "orders"] else "inventory"
        }

    def _parse_time_period(self, time_period: str) -> str:
        """Convert natural language time period to ShopifyQL"""
        if not time_period:
            return "SINCE -7d UNTIL today"

        time_period = time_period.lower()

        if "30 day" in time_period or "month" in time_period:
            return "SINCE -30d UNTIL today"
        elif "90 day" in time_period or "3 month" in time_period:
            return "SINCE -90d UNTIL today"
        elif "year" in time_period or "365" in time_period:
            return "SINCE -1y UNTIL today"
        elif "week" in time_period or "7 day" in time_period:
            return "SINCE -7d UNTIL today"
        elif "today" in time_period:
            return "SINCE today UNTIL today"
        elif "yesterday" in time_period:
            return "SINCE -1d UNTIL -1d"
        else:
            return "SINCE -7d UNTIL today"
