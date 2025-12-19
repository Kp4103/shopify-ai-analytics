# frozen_string_literal: true

# AuthController - Handles Shopify OAuth authentication
#
# OAuth Flow:
# 1. GET /auth/shopify?shop=store-name.myshopify.com
#    - Redirects to Shopify authorization page
# 2. GET /auth/shopify/callback
#    - Receives authorization code
#    - Exchanges for access token
#    - Stores credentials
#
class AuthController < ApplicationController
  SHOPIFY_API_KEY = ENV.fetch("SHOPIFY_API_KEY", nil)
  SHOPIFY_API_SECRET = ENV.fetch("SHOPIFY_API_SECRET", nil)
  SCOPES = "read_orders,read_products,read_inventory,read_customers"

  def shopify
    shop = params[:shop]

    unless shop.present?
      return render json: { error: "Missing shop parameter" }, status: :bad_request
    end

    # Normalize shop domain
    shop = Store.normalize_domain(shop)

    # Generate nonce for CSRF protection
    nonce = SecureRandom.hex(16)
    session[:shopify_nonce] = nonce

    # Build authorization URL
    redirect_uri = callback_url
    auth_url = build_auth_url(shop, redirect_uri, nonce)

    redirect_to auth_url, allow_other_host: true
  end

  def callback
    # Verify the request
    unless valid_callback?
      return render json: { error: "Invalid callback request" }, status: :bad_request
    end

    shop = params[:shop]
    code = params[:code]

    # Exchange code for access token
    token_response = exchange_code_for_token(shop, code)

    if token_response[:error]
      return render json: { error: token_response[:error] }, status: :bad_request
    end

    # Store or update the store record
    store = Store.find_or_initialize_by(shop_domain: Store.normalize_domain(shop))
    store.assign_attributes(
      access_token: token_response[:access_token],
      scopes: token_response[:scope],
      active: true
    )
    store.save!

    # Return success response
    render json: {
      success: true,
      message: "Successfully connected to #{shop}",
      store_id: store.shop_domain
    }
  end

  private

  def build_auth_url(shop, redirect_uri, nonce)
    params = {
      client_id: SHOPIFY_API_KEY,
      scope: SCOPES,
      redirect_uri: redirect_uri,
      state: nonce
    }

    "https://#{shop}/admin/oauth/authorize?#{params.to_query}"
  end

  def callback_url
    url_for(action: :callback, only_path: false)
  end

  def valid_callback?
    # Verify HMAC
    return false unless valid_hmac?

    # Verify nonce (state parameter)
    return false unless params[:state] == session[:shopify_nonce]

    # Verify required params
    params[:shop].present? && params[:code].present?
  end

  def valid_hmac?
    return true if Rails.env.development? && params[:hmac].blank?

    hmac = params[:hmac]
    return false unless hmac.present?

    # Build the message to verify
    query_params = request.query_parameters.except(:hmac)
    message = query_params.sort.map { |k, v| "#{k}=#{v}" }.join("&")

    # Calculate expected HMAC
    digest = OpenSSL::HMAC.hexdigest("SHA256", SHOPIFY_API_SECRET, message)

    # Secure comparison
    ActiveSupport::SecurityUtils.secure_compare(digest, hmac)
  end

  def exchange_code_for_token(shop, code)
    url = "https://#{shop}/admin/oauth/access_token"

    response = HTTParty.post(url, {
      body: {
        client_id: SHOPIFY_API_KEY,
        client_secret: SHOPIFY_API_SECRET,
        code: code
      }.to_json,
      headers: { "Content-Type" => "application/json" }
    })

    if response.success?
      {
        access_token: response["access_token"],
        scope: response["scope"]
      }
    else
      { error: "Failed to exchange code for token: #{response.body}" }
    end
  end
end
