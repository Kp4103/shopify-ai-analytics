# frozen_string_literal: true

module Api
  module V1
    class StoresController < BaseController
      skip_before_action :authenticate_store!, only: [:index]

      def index
        stores = Store.active.select(:id, :shop_domain, :created_at)

        render json: {
          stores: stores.map do |store|
            {
              shop_domain: store.shop_domain,
              connected_at: store.created_at.iso8601
            }
          end
        }
      end

      def show
        render json: {
          shop_domain: @current_store.shop_domain,
          scopes: @current_store.scopes,
          connected: @current_store.connected?,
          api_version: @current_store.api_version
        }
      end

      def test_connection
        client = ShopifyApiService.new(@current_store)
        result = client.test_connection

        if result[:success]
          render json: {
            success: true,
            shop_name: result[:shop_name],
            email: result[:email]
          }
        else
          render json: {
            success: false,
            error: result[:error]
          }, status: :service_unavailable
        end
      end
    end
  end
end
