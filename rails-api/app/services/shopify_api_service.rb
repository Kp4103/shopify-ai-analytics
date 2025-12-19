# frozen_string_literal: true

# ShopifyApiService - Direct Shopify API client
#
# Used for testing connections and making direct Shopify API calls
# when needed (though most queries go through the Python AI service).
#
class ShopifyApiService
  class ApiError < StandardError; end

  def initialize(store)
    @store = store
    @graphql_url = store.graphql_url
    @headers = {
      "X-Shopify-Access-Token" => store.access_token,
      "Content-Type" => "application/json"
    }
  end

  # Test the connection to Shopify
  #
  # @return [Hash] Connection test result
  #
  def test_connection
    query = <<~GRAPHQL
      query {
        shop {
          name
          email
          myshopifyDomain
        }
      }
    GRAPHQL

    result = execute_query(query)

    if result[:error]
      { success: false, error: result[:error] }
    else
      shop = result.dig(:data, "shop")
      {
        success: true,
        shop_name: shop["name"],
        email: shop["email"],
        domain: shop["myshopifyDomain"]
      }
    end
  end

  # Get recent orders
  #
  # @param limit [Integer] Maximum orders to return
  # @return [Array<Hash>] List of orders
  #
  def get_orders(limit: 10)
    query = <<~GRAPHQL
      query getOrders($first: Int!) {
        orders(first: $first, sortKey: CREATED_AT, reverse: true) {
          edges {
            node {
              id
              name
              createdAt
              totalPriceSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
            }
          }
        }
      }
    GRAPHQL

    result = execute_query(query, { first: limit })

    return [] if result[:error]

    result.dig(:data, "orders", "edges")&.map { |e| e["node"] } || []
  end

  # Get products
  #
  # @param limit [Integer] Maximum products to return
  # @return [Array<Hash>] List of products
  #
  def get_products(limit: 10)
    query = <<~GRAPHQL
      query getProducts($first: Int!) {
        products(first: $first) {
          edges {
            node {
              id
              title
              handle
              totalInventory
            }
          }
        }
      }
    GRAPHQL

    result = execute_query(query, { first: limit })

    return [] if result[:error]

    result.dig(:data, "products", "edges")&.map { |e| e["node"] } || []
  end

  private

  def execute_query(query, variables = {})
    response = HTTParty.post(
      @graphql_url,
      body: { query: query, variables: variables }.to_json,
      headers: @headers,
      timeout: 30
    )

    if response.success?
      parsed = response.parsed_response

      if parsed["errors"]
        error_messages = parsed["errors"].map { |e| e["message"] }.join(", ")
        { error: error_messages }
      else
        { data: parsed["data"] }
      end
    else
      { error: "HTTP #{response.code}: #{response.message}" }
    end
  rescue StandardError => e
    Rails.logger.error("Shopify API error: #{e.message}")
    { error: e.message }
  end
end
