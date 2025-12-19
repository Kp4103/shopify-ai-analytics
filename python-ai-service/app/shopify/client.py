"""
Shopify Client - Handles all Shopify API interactions

Supports both GraphQL Admin API and ShopifyQL analytics queries.
Implements a fallback chain: ShopifyQL (primary) -> GraphQL (fallback)
"""
import httpx
from typing import Dict, Any, Optional, List
import structlog

from app.config import settings

logger = structlog.get_logger()


class ShopifyClient:
    """Client for interacting with Shopify APIs with fallback support"""

    # Error patterns that indicate ShopifyQL is not available
    SHOPIFYQL_UNAVAILABLE_ERRORS = [
        "shopifyqlQuery",
        "doesn't exist on type",
        "not available",
        "not supported"
    ]

    def __init__(self, store_domain: str, access_token: str):
        """
        Initialize the Shopify client.

        Args:
            store_domain: The store's myshopify.com domain
            access_token: OAuth access token for the store
        """
        self.store_domain = store_domain.replace("https://", "").replace("http://", "")
        if not self.store_domain.endswith(".myshopify.com"):
            self.store_domain = f"{self.store_domain}.myshopify.com"

        self.access_token = access_token
        self.api_version = settings.SHOPIFY_API_VERSION
        self.graphql_url = f"https://{self.store_domain}/admin/api/{self.api_version}/graphql.json"

        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

    async def execute_query_with_fallback(
        self,
        shopifyql_query: str,
        intent: str,
        entities: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a query with ShopifyQL as primary and GraphQL as fallback.

        Args:
            shopifyql_query: The ShopifyQL query to try first
            intent: The classified intent (sales, inventory, customers, orders)
            entities: Extracted entities for fallback query generation

        Returns:
            Dictionary with query results, source indicator, and any errors
        """
        entities = entities or {}

        # Step 1: Try ShopifyQL first
        logger.info("attempting_shopifyql", query=shopifyql_query[:100])
        shopifyql_result = await self.execute_shopifyql(shopifyql_query)

        # Check if ShopifyQL succeeded
        if not shopifyql_result.get("error"):
            logger.info("shopifyql_success")
            return {
                **shopifyql_result,
                "source": "shopifyql",
                "fallback_used": False
            }

        # Step 2: Check if error indicates ShopifyQL is unavailable
        error_msg = shopifyql_result.get("error", "").lower()
        is_shopifyql_unavailable = any(
            pattern.lower() in error_msg
            for pattern in self.SHOPIFYQL_UNAVAILABLE_ERRORS
        )

        if is_shopifyql_unavailable:
            logger.info(
                "shopifyql_unavailable_falling_back_to_graphql",
                error=shopifyql_result.get("error")
            )

            # Step 3: Fall back to GraphQL
            graphql_result = await self.execute_graphql_fallback(intent, entities)

            return {
                **graphql_result,
                "source": "graphql_fallback",
                "fallback_used": True,
                "shopifyql_error": shopifyql_result.get("error"),
                "original_query": shopifyql_query
            }

        # ShopifyQL failed for other reasons (syntax error, etc.)
        logger.warning("shopifyql_failed", error=shopifyql_result.get("error"))
        return {
            **shopifyql_result,
            "source": "shopifyql",
            "fallback_used": False
        }

    async def execute_graphql_fallback(
        self,
        intent: str,
        entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a GraphQL query as fallback when ShopifyQL is unavailable.

        Args:
            intent: The classified intent
            entities: Extracted entities from the question

        Returns:
            Dictionary with query results
        """
        logger.info("executing_graphql_fallback", intent=intent)

        if intent == "inventory":
            return await self._graphql_inventory_query(entities)
        elif intent == "sales" or intent == "orders":
            return await self._graphql_orders_query(entities)
        elif intent == "customers":
            return await self._graphql_customers_query(entities)
        else:
            # Default to products
            return await self._graphql_products_query(entities)

    async def _graphql_products_query(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch products with inventory data via GraphQL"""
        limit = entities.get("limit", 10) or 10

        query = """
        query getProducts($first: Int!) {
            products(first: $first, sortKey: INVENTORY_TOTAL, reverse: true) {
                edges {
                    node {
                        id
                        title
                        handle
                        productType
                        vendor
                        totalInventory
                        status
                        variants(first: 5) {
                            edges {
                                node {
                                    id
                                    title
                                    price
                                    inventoryQuantity
                                    sku
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": {"first": min(limit, 50)}},
                    headers=self.headers
                )
                response.raise_for_status()
                result = response.json()

                if "errors" in result:
                    return {"error": result["errors"][0].get("message"), "data": []}

                products = []
                edges = result.get("data", {}).get("products", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    variant = node.get("variants", {}).get("edges", [{}])[0].get("node", {})
                    products.append({
                        "product_title": node.get("title"),
                        "product_type": node.get("productType"),
                        "vendor": node.get("vendor"),
                        "total_inventory": node.get("totalInventory"),
                        "price": variant.get("price"),
                        "sku": variant.get("sku"),
                        "status": node.get("status")
                    })

                return {"data": products}

        except Exception as e:
            logger.error("graphql_products_error", error=str(e))
            return {"error": str(e), "data": []}

    async def _graphql_inventory_query(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch inventory levels via GraphQL"""
        limit = entities.get("limit", 20) or 20
        product_name = entities.get("product_name")

        # Build query filter if product name specified
        query_filter = ""
        if product_name:
            query_filter = f', query: "title:*{product_name}*"'

        query = f"""
        query getInventory($first: Int!) {{
            products(first: $first, sortKey: INVENTORY_TOTAL{query_filter}) {{
                edges {{
                    node {{
                        id
                        title
                        totalInventory
                        variants(first: 10) {{
                            edges {{
                                node {{
                                    id
                                    title
                                    inventoryQuantity
                                    price
                                    sku
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": {"first": min(limit, 50)}},
                    headers=self.headers
                )
                response.raise_for_status()
                result = response.json()

                if "errors" in result:
                    return {"error": result["errors"][0].get("message"), "data": []}

                inventory_data = []
                edges = result.get("data", {}).get("products", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    for variant_edge in node.get("variants", {}).get("edges", []):
                        variant = variant_edge.get("node", {})
                        inventory_data.append({
                            "product_title": node.get("title"),
                            "variant_title": variant.get("title"),
                            "quantity_available": variant.get("inventoryQuantity"),
                            "price": variant.get("price"),
                            "sku": variant.get("sku")
                        })

                # Sort by quantity (low stock first)
                inventory_data.sort(key=lambda x: x.get("quantity_available", 0))

                return {"data": inventory_data}

        except Exception as e:
            logger.error("graphql_inventory_error", error=str(e))
            return {"error": str(e), "data": []}

    async def _graphql_orders_query(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch orders via GraphQL"""
        limit = entities.get("limit", 20) or 20

        query = """
        query getOrders($first: Int!) {
            orders(first: $first, sortKey: CREATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        name
                        createdAt
                        displayFinancialStatus
                        displayFulfillmentStatus
                        totalPriceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        customer {
                            displayName
                            email
                        }
                        lineItems(first: 10) {
                            edges {
                                node {
                                    title
                                    quantity
                                    originalUnitPriceSet {
                                        shopMoney {
                                            amount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": {"first": min(limit, 50)}},
                    headers=self.headers
                )
                response.raise_for_status()
                result = response.json()

                if "errors" in result:
                    return {"error": result["errors"][0].get("message"), "data": []}

                orders_data = []
                total_revenue = 0
                product_sales = {}

                edges = result.get("data", {}).get("orders", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    amount = float(node.get("totalPriceSet", {}).get("shopMoney", {}).get("amount", 0))
                    total_revenue += amount

                    # Aggregate product sales
                    for item_edge in node.get("lineItems", {}).get("edges", []):
                        item = item_edge.get("node", {})
                        title = item.get("title", "Unknown")
                        qty = item.get("quantity", 0)
                        price = float(item.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount", 0))

                        if title not in product_sales:
                            product_sales[title] = {"units_sold": 0, "revenue": 0}
                        product_sales[title]["units_sold"] += qty
                        product_sales[title]["revenue"] += qty * price

                    orders_data.append({
                        "order_name": node.get("name"),
                        "created_at": node.get("createdAt"),
                        "total_amount": amount,
                        "currency": node.get("totalPriceSet", {}).get("shopMoney", {}).get("currencyCode"),
                        "status": node.get("displayFinancialStatus"),
                        "fulfillment": node.get("displayFulfillmentStatus"),
                        "customer": node.get("customer", {}).get("displayName")
                    })

                # Convert product sales to list and sort
                product_sales_list = [
                    {
                        "product_title": title,
                        "units_sold": data["units_sold"],
                        "total_sales": round(data["revenue"], 2)
                    }
                    for title, data in product_sales.items()
                ]
                product_sales_list.sort(key=lambda x: x["total_sales"], reverse=True)

                return {
                    "data": product_sales_list[:limit],
                    "orders": orders_data,
                    "summary": {
                        "total_orders": len(orders_data),
                        "total_revenue": round(total_revenue, 2)
                    }
                }

        except Exception as e:
            logger.error("graphql_orders_error", error=str(e))
            return {"error": str(e), "data": []}

    async def _graphql_customers_query(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch customer data via GraphQL"""
        limit = entities.get("limit", 20) or 20

        query = """
        query getCustomers($first: Int!) {
            customers(first: $first, sortKey: UPDATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        displayName
                        email
                        ordersCount
                        totalSpent
                        createdAt
                        defaultAddress {
                            city
                            country
                        }
                    }
                }
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": {"first": min(limit, 50)}},
                    headers=self.headers
                )
                response.raise_for_status()
                result = response.json()

                if "errors" in result:
                    return {"error": result["errors"][0].get("message"), "data": []}

                customers_data = []
                edges = result.get("data", {}).get("customers", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    address = node.get("defaultAddress") or {}
                    customers_data.append({
                        "customer_name": node.get("displayName"),
                        "email": node.get("email"),
                        "orders_count": node.get("ordersCount"),
                        "total_spent": node.get("totalSpent"),
                        "city": address.get("city"),
                        "country": address.get("country"),
                        "created_at": node.get("createdAt")
                    })

                # Filter repeat customers if needed
                repeat_customers = [c for c in customers_data if (c.get("orders_count") or 0) > 1]

                return {
                    "data": customers_data,
                    "repeat_customers": repeat_customers,
                    "summary": {
                        "total_customers": len(customers_data),
                        "repeat_customers": len(repeat_customers)
                    }
                }

        except Exception as e:
            logger.error("graphql_customers_error", error=str(e))
            return {"error": str(e), "data": []}

    async def execute_shopifyql(self, query: str) -> Dict[str, Any]:
        """
        Execute a ShopifyQL query against the store.

        Args:
            query: The ShopifyQL query string

        Returns:
            Dictionary with query results or error
        """
        # ShopifyQL is executed via GraphQL mutation
        graphql_query = """
        mutation shopifyqlQuery($query: String!) {
            shopifyqlQuery(query: $query) {
                __typename
                ... on TableResponse {
                    tableData {
                        unformattedData
                        rowData
                        columns {
                            name
                            dataType
                            displayName
                        }
                    }
                    parseErrors {
                        code
                        message
                        range {
                            start { line character }
                            end { line character }
                        }
                    }
                }
                ... on PolarisVizResponse {
                    data {
                        key
                        data {
                            key
                            value
                        }
                    }
                    parseErrors {
                        code
                        message
                    }
                }
            }
        }
        """

        variables = {"query": query}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": graphql_query, "variables": variables},
                    headers=self.headers
                )

                response.raise_for_status()
                result = response.json()

                logger.info(
                    "shopifyql_executed",
                    store=self.store_domain,
                    status=response.status_code
                )

                # Process the response
                return self._process_shopifyql_response(result)

        except httpx.HTTPStatusError as e:
            logger.error(
                "shopifyql_http_error",
                status=e.response.status_code,
                detail=str(e)
            )
            return {"error": f"HTTP error: {e.response.status_code}", "data": []}

        except Exception as e:
            logger.error("shopifyql_error", error=str(e))
            return {"error": str(e), "data": []}

    def _process_shopifyql_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Process and normalize the ShopifyQL response"""
        if "errors" in result:
            error_messages = [e.get("message", str(e)) for e in result["errors"]]
            return {"error": "; ".join(error_messages), "data": []}

        data = result.get("data", {})
        shopifyql_result = data.get("shopifyqlQuery", {})

        if not shopifyql_result:
            return {"error": "No data in response", "data": []}

        # Handle parse errors
        parse_errors = shopifyql_result.get("parseErrors", [])
        if parse_errors:
            error_messages = [e.get("message", "Parse error") for e in parse_errors]
            return {"error": "; ".join(error_messages), "data": [], "parse_errors": parse_errors}

        # Handle TableResponse
        if shopifyql_result.get("__typename") == "TableResponse":
            table_data = shopifyql_result.get("tableData", {})
            return self._process_table_response(table_data)

        # Handle PolarisVizResponse
        if shopifyql_result.get("__typename") == "PolarisVizResponse":
            viz_data = shopifyql_result.get("data", [])
            return self._process_viz_response(viz_data)

        return {"error": "Unknown response type", "data": []}

    def _process_table_response(self, table_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process TableResponse data into a list of dictionaries"""
        columns = table_data.get("columns", [])
        row_data = table_data.get("rowData", [])

        if not columns or not row_data:
            return {"data": [], "tableData": table_data}

        # Convert to list of dictionaries
        column_names = [col.get("name", f"col_{i}") for i, col in enumerate(columns)]
        data = []

        for row in row_data:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(column_names):
                    row_dict[column_names[i]] = value
            data.append(row_dict)

        return {
            "data": data,
            "columns": columns,
            "tableData": table_data
        }

    def _process_viz_response(self, viz_data: List[Dict]) -> Dict[str, Any]:
        """Process PolarisVizResponse data"""
        data = []
        for series in viz_data:
            series_key = series.get("key", "unknown")
            for point in series.get("data", []):
                data.append({
                    "series": series_key,
                    "key": point.get("key"),
                    "value": point.get("value")
                })

        return {"data": data}

    async def get_products(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch products from the store"""
        result = await self._graphql_products_query({"limit": limit})
        return result.get("data", [])

    async def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent orders from the store"""
        result = await self._graphql_orders_query({"limit": limit})
        return result.get("orders", [])

    async def test_connection(self) -> bool:
        """Test if the connection to Shopify is working"""
        query = """
        query {
            shop {
                name
                email
            }
        }
        """

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query},
                    headers=self.headers
                )
                response.raise_for_status()
                result = response.json()

                shop = result.get("data", {}).get("shop", {})
                if shop:
                    logger.info("shopify_connection_success", shop=shop.get("name"))
                    return True

                return False

        except Exception as e:
            logger.error("shopify_connection_failed", error=str(e))
            return False
