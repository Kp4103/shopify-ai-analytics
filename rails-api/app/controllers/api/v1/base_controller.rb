# frozen_string_literal: true

module Api
  module V1
    class BaseController < ApplicationController
      before_action :authenticate_store!

      private

      def authenticate_store!
        store_id = params[:store_id] || request.headers["X-Store-ID"]

        unless store_id.present?
          return render json: { error: "Missing store_id parameter" }, status: :bad_request
        end

        @current_store = Store.find_by_domain(store_id)

        unless @current_store&.connected?
          render json: {
            error: "Store not found or not connected",
            message: "Please authenticate via /auth/shopify?shop=#{store_id}"
          }, status: :unauthorized
        end
      end
    end
  end
end
