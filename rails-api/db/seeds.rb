# Create the store record using environment variables
# Set SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN in your .env file
if ENV["SHOPIFY_STORE_DOMAIN"].present? && ENV["SHOPIFY_ACCESS_TOKEN"].present?
  Store.find_or_create_by!(shop_domain: ENV["SHOPIFY_STORE_DOMAIN"]) do |store|
    store.access_token = ENV["SHOPIFY_ACCESS_TOKEN"]
    store.scopes = "read_orders,read_products,read_inventory,read_customers,write_products"
    store.active = true
  end
  puts "Store created successfully!"
else
  puts "Skipping seed: Set SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN environment variables"
end
