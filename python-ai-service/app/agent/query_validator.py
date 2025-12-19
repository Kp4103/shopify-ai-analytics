"""
Query Validator - Validates ShopifyQL queries before execution

Performs syntax validation and checks for common errors to ensure
queries will execute successfully against the Shopify API.
"""
import re
from typing import Tuple, List
import structlog

logger = structlog.get_logger()


class QueryValidator:
    """Validates ShopifyQL queries for syntax and semantic correctness"""

    # Valid tables in ShopifyQL
    VALID_TABLES = ["sales", "products", "inventory"]

    # Valid fields by table
    VALID_FIELDS = {
        "sales": [
            "order_id", "product_id", "product_title", "product_type",
            "variant_id", "variant_title", "billing_city", "billing_country",
            "billing_region", "shipping_city", "shipping_country",
            "net_sales", "gross_sales", "discounts", "returns", "taxes",
            "total_sales", "net_quantity", "ordered_quantity", "returned_quantity",
            "day", "hour", "month", "week", "year"
        ],
        "products": [
            "product_id", "product_title", "product_type", "vendor", "product_tag"
        ],
        "inventory": [
            "product_id", "product_title", "variant_id", "variant_title",
            "quantity_available", "incoming_quantity", "committed_quantity",
            "location_id", "location_name"
        ]
    }

    # Valid aggregate functions
    AGGREGATE_FUNCTIONS = ["sum", "count", "avg", "min", "max"]

    # Required clauses
    REQUIRED_CLAUSES = ["FROM", "SHOW"]

    def validate(self, query: str) -> Tuple[bool, List[str]]:
        """
        Validate a ShopifyQL query.

        Args:
            query: The ShopifyQL query string

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not query or not query.strip():
            return False, ["Query is empty"]

        query = query.strip()

        # Check for required clauses
        errors.extend(self._check_required_clauses(query))

        # Check table validity
        errors.extend(self._check_table(query))

        # Check field validity
        errors.extend(self._check_fields(query))

        # Check syntax structure
        errors.extend(self._check_syntax(query))

        # Check time expressions
        errors.extend(self._check_time_expressions(query))

        is_valid = len(errors) == 0

        if not is_valid:
            logger.warning("query_validation_failed", errors=errors, query=query[:200])

        return is_valid, errors

    def _check_required_clauses(self, query: str) -> List[str]:
        """Check that required clauses are present"""
        errors = []
        query_upper = query.upper()

        for clause in self.REQUIRED_CLAUSES:
            if clause not in query_upper:
                errors.append(f"Missing required clause: {clause}")

        return errors

    def _check_table(self, query: str) -> List[str]:
        """Check that the table is valid"""
        errors = []

        # Extract table name after FROM
        match = re.search(r"FROM\s+(\w+)", query, re.IGNORECASE)
        if match:
            table = match.group(1).lower()
            if table not in self.VALID_TABLES:
                errors.append(f"Invalid table: '{table}'. Valid tables are: {', '.join(self.VALID_TABLES)}")
        else:
            errors.append("Could not find table name after FROM clause")

        return errors

    def _check_fields(self, query: str) -> List[str]:
        """Check that fields are valid for the specified table"""
        errors = []

        # Get the table
        table_match = re.search(r"FROM\s+(\w+)", query, re.IGNORECASE)
        if not table_match:
            return errors

        table = table_match.group(1).lower()
        if table not in self.VALID_FIELDS:
            return errors

        valid_fields = self.VALID_FIELDS[table]

        # Extract fields from SHOW clause
        show_match = re.search(r"SHOW\s+(.+?)(?:WHERE|GROUP|ORDER|SINCE|LIMIT|$)", query, re.IGNORECASE | re.DOTALL)
        if show_match:
            show_clause = show_match.group(1)

            # Extract field names (handle aggregates like sum(field))
            # Match field names, including those inside aggregate functions
            fields_found = re.findall(r"(?:sum|count|avg|min|max)\s*\(\s*(\w+)\s*\)|(\w+)", show_clause, re.IGNORECASE)

            for match in fields_found:
                field = match[0] or match[1]
                field = field.lower()

                # Skip keywords and aliases
                if field in ["as", "asc", "desc"] or field in self.AGGREGATE_FUNCTIONS:
                    continue

                # Skip numeric values
                if field.isdigit():
                    continue

                # Check if field is valid (allowing for some flexibility with aliases)
                if field not in valid_fields and not self._is_alias_or_literal(field, show_clause):
                    # Only warn, don't error - LLM might use valid fields we don't know about
                    logger.debug("potential_invalid_field", field=field, table=table)

        return errors

    def _is_alias_or_literal(self, field: str, clause: str) -> bool:
        """Check if a field name is likely an alias or literal"""
        # Check if it appears after AS
        pattern = rf"AS\s+{field}"
        return bool(re.search(pattern, clause, re.IGNORECASE))

    def _check_syntax(self, query: str) -> List[str]:
        """Check general syntax structure"""
        errors = []
        query_upper = query.upper()

        # Check clause order (FROM should come before SHOW in some versions)
        # Actually in ShopifyQL, FROM comes first
        from_pos = query_upper.find("FROM")
        show_pos = query_upper.find("SHOW")

        if from_pos > show_pos and from_pos != -1 and show_pos != -1:
            errors.append("FROM clause should come before SHOW clause")

        # Check for balanced parentheses
        if query.count("(") != query.count(")"):
            errors.append("Unbalanced parentheses in query")

        # Check GROUP BY if aggregates are used
        has_aggregate = any(f"{func}(" in query.lower() for func in self.AGGREGATE_FUNCTIONS)
        has_group_by = "GROUP BY" in query_upper

        # Check for non-aggregated fields when using aggregates without GROUP BY
        if has_aggregate and not has_group_by:
            # This is often valid in ShopifyQL, so just log a warning
            logger.debug("aggregate_without_group_by", query=query[:100])

        return errors

    def _check_time_expressions(self, query: str) -> List[str]:
        """Check time expression syntax"""
        errors = []
        query_upper = query.upper()

        # If SINCE is used, check format
        if "SINCE" in query_upper:
            # Valid formats: SINCE -7d, SINCE -1m, SINCE -1y, SINCE today
            since_match = re.search(r"SINCE\s+(\S+)", query, re.IGNORECASE)
            if since_match:
                since_value = since_match.group(1)
                valid_patterns = [
                    r"^-\d+[dmy]$",  # -7d, -1m, -1y
                    r"^today$",
                    r"^yesterday$",
                    r"^-\d+$"  # Just days
                ]
                if not any(re.match(p, since_value, re.IGNORECASE) for p in valid_patterns):
                    logger.debug("unusual_time_expression", since_value=since_value)

        # If UNTIL is used without SINCE, that might be an issue
        if "UNTIL" in query_upper and "SINCE" not in query_upper:
            errors.append("UNTIL clause used without SINCE clause")

        return errors

    def suggest_fix(self, query: str, errors: List[str]) -> str:
        """Suggest fixes for common errors"""
        suggestions = []

        for error in errors:
            if "Missing required clause: FROM" in error:
                suggestions.append("Add 'FROM <table>' clause (e.g., FROM sales)")
            elif "Missing required clause: SHOW" in error:
                suggestions.append("Add 'SHOW <fields>' clause to specify what data to return")
            elif "Invalid table" in error:
                suggestions.append(f"Use one of the valid tables: {', '.join(self.VALID_TABLES)}")
            elif "Unbalanced parentheses" in error:
                suggestions.append("Check that all opening parentheses have matching closing ones")

        return "; ".join(suggestions) if suggestions else "Review query syntax"
