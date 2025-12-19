"""
Response Formatter - Converts raw query results into business-friendly language

Takes the raw data from ShopifyQL queries and transforms it into
human-readable insights with actionable recommendations.
"""
import json
from typing import Dict, Any, List, Optional
import structlog

from app.llm.gemini_client import GeminiClient

logger = structlog.get_logger()

RESPONSE_FORMATTING_PROMPT = """You are a helpful business analytics assistant. Convert the following data into a clear, friendly response for a store owner.

Original Question: {question}
Intent Category: {intent}
Query Data: {data}

Guidelines:
1. Speak in simple, business-friendly language - no technical jargon
2. IMPORTANT: Answer the question that was asked. If they ask to "list products" or "what products", list ALL the products with their details
3. If asked about inventory/stock, show all products with their stock levels
4. Include specific numbers and percentages where relevant
5. If data suggests action items (like low stock), mention them as additional insights
6. Be conversational but professional
7. If the data is empty or insufficient, explain what that means
8. Format numbers nicely (e.g., "$1,234.56" not "1234.56")
9. Round percentages to one decimal place

Respond in JSON format:
{{
    "answer": "Your friendly, conversational response here",
    "confidence": "high|medium|low",
    "key_insights": ["insight 1", "insight 2"],
    "recommendations": ["recommendation 1"] (optional)
}}
"""


class ResponseFormatter:
    """Formats query results into business-friendly responses"""

    def __init__(self):
        self.llm = GeminiClient()

    async def format(
        self,
        question: str,
        intent: str,
        query_data: Dict[str, Any],
        entities: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Format query results into a human-readable response.

        Args:
            question: Original user question
            intent: Classified intent
            query_data: Raw data from ShopifyQL query
            entities: Extracted entities from the question

        Returns:
            Dictionary with formatted answer and metadata
        """
        # Handle empty or error data
        if not query_data or query_data.get("error"):
            return self._format_empty_response(question, query_data)

        # Prepare data summary for the LLM
        data_summary = self._prepare_data_summary(query_data)

        prompt = RESPONSE_FORMATTING_PROMPT.format(
            question=question,
            intent=intent,
            data=data_summary
        )

        try:
            response = await self.llm.generate(prompt)
            result = self._parse_response(response)

            logger.info(
                "response_formatted",
                confidence=result.get("confidence"),
                has_recommendations=bool(result.get("recommendations"))
            )

            return result

        except Exception as e:
            logger.error("response_formatting_error", error=str(e))
            # Generate a basic response from the data
            return self._generate_basic_response(question, query_data, intent)

    def _prepare_data_summary(self, query_data: Dict[str, Any]) -> str:
        """Prepare a summary of the data for the LLM"""
        data = query_data.get("data", [])

        if not data:
            return "No data returned from query"

        # Limit data size for LLM context
        if len(data) > 20:
            summary_data = data[:20]
            truncated = True
        else:
            summary_data = data
            truncated = False

        summary = json.dumps(summary_data, indent=2, default=str)

        if truncated:
            summary += f"\n\n... and {len(data) - 20} more rows"

        # Add metadata if available
        if "tableData" in query_data:
            table_data = query_data["tableData"]
            if "rowData" in table_data:
                summary = f"Rows returned: {len(table_data['rowData'])}\n\n{summary}"

        return summary

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM response"""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response.strip())

            if "answer" not in result:
                result["answer"] = response

            return result

        except json.JSONDecodeError:
            # If JSON parsing fails, use the response as-is
            return {
                "answer": response,
                "confidence": "medium",
                "key_insights": []
            }

    def _format_empty_response(
        self,
        question: str,
        query_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format a response when there's no data"""
        if query_data and query_data.get("error"):
            error_msg = query_data["error"]
            return {
                "answer": f"I wasn't able to retrieve the data you requested. The issue was: {error_msg}. Please try rephrasing your question or check that the store has the relevant data.",
                "confidence": "low",
                "key_insights": []
            }

        return {
            "answer": "I couldn't find any data matching your question. This could mean there are no records for the time period you specified, or the specific items you're asking about don't exist in the store. Try broadening your search or checking a different time range.",
            "confidence": "low",
            "key_insights": []
        }

    def _generate_basic_response(
        self,
        question: str,
        query_data: Dict[str, Any],
        intent: str
    ) -> Dict[str, Any]:
        """Generate a basic response without LLM"""
        data = query_data.get("data", [])

        if not data:
            return self._format_empty_response(question, None)

        # Build a simple response based on intent
        if intent == "sales":
            return self._format_sales_response(data)
        elif intent == "inventory":
            return self._format_inventory_response(data)
        elif intent == "customers":
            return self._format_customer_response(data)
        else:
            return self._format_generic_response(data)

    def _format_sales_response(self, data: List[Dict]) -> Dict[str, Any]:
        """Format a basic sales response"""
        if not data:
            return {"answer": "No sales data found.", "confidence": "medium"}

        # Try to extract key metrics
        total_sales = sum(float(row.get("total_sales", 0) or row.get("net_sales", 0) or 0) for row in data)
        total_units = sum(int(row.get("units_sold", 0) or row.get("net_quantity", 0) or 0) for row in data)

        answer = f"Based on the data, your total sales were ${total_sales:,.2f}"
        if total_units > 0:
            answer += f" with {total_units:,} units sold"
        answer += "."

        if len(data) > 1 and "product_title" in data[0]:
            top_product = data[0].get("product_title", "Unknown")
            answer += f" Your top performing product was {top_product}."

        return {
            "answer": answer,
            "confidence": "medium",
            "key_insights": [f"Total sales: ${total_sales:,.2f}"]
        }

    def _format_inventory_response(self, data: List[Dict]) -> Dict[str, Any]:
        """Format a basic inventory response"""
        if not data:
            return {"answer": "No inventory data found.", "confidence": "medium"}

        # Build product list
        products_info = []
        low_stock_items = []

        for row in data:
            stock = int(row.get("stock", 0) or row.get("quantity_available", 0) or 0)
            product = row.get("product_title", "Unknown")
            price = row.get("price", "N/A")

            if price and price != "N/A":
                products_info.append(f"• {product}: {stock} units @ ${price}")
            else:
                products_info.append(f"• {product}: {stock} units")

            if stock < 10:
                low_stock_items.append(f"{product} ({stock} units)")

        # Build comprehensive response
        answer = f"Here are your {len(data)} products:\n\n" + "\n".join(products_info[:10])

        if len(products_info) > 10:
            answer += f"\n... and {len(products_info) - 10} more products."

        if low_stock_items:
            answer += f"\n\n⚠️ Low stock alert: {', '.join(low_stock_items[:3])}"

        return {
            "answer": answer,
            "confidence": "medium",
            "key_insights": [f"{len(data)} products", f"{len(low_stock_items)} items with low stock"]
        }

    def _format_customer_response(self, data: List[Dict]) -> Dict[str, Any]:
        """Format a basic customer response"""
        if not data:
            return {"answer": "No customer data found.", "confidence": "medium"}

        total_customers = len(data)
        answer = f"Found data for {total_customers} customer segments or locations."

        return {
            "answer": answer,
            "confidence": "medium",
            "key_insights": [f"{total_customers} segments found"]
        }

    def _format_generic_response(self, data: List[Dict]) -> Dict[str, Any]:
        """Format a generic response"""
        row_count = len(data)
        answer = f"Found {row_count} records matching your query."

        if row_count > 0 and data[0]:
            columns = list(data[0].keys())
            answer += f" Data includes: {', '.join(columns[:5])}"
            if len(columns) > 5:
                answer += f" and {len(columns) - 5} more fields."

        return {
            "answer": answer,
            "confidence": "medium",
            "key_insights": [f"{row_count} records found"]
        }
