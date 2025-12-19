# frozen_string_literal: true

class ApplicationController < ActionController::API
  include ActionController::HttpAuthentication::Token::ControllerMethods

  rescue_from StandardError, with: :handle_error
  rescue_from ActiveRecord::RecordNotFound, with: :not_found
  rescue_from ActionController::ParameterMissing, with: :bad_request

  private

  def handle_error(exception)
    Rails.logger.error("Unhandled error: #{exception.message}")
    Rails.logger.error(exception.backtrace.first(10).join("\n"))

    render json: {
      error: "Internal server error",
      message: Rails.env.development? ? exception.message : "An unexpected error occurred"
    }, status: :internal_server_error
  end

  def not_found
    render json: { error: "Resource not found" }, status: :not_found
  end

  def bad_request(exception)
    render json: {
      error: "Bad request",
      message: exception.message
    }, status: :bad_request
  end

  def authenticate_store!
    @current_store = Store.find_by_domain(params[:store_id])

    unless @current_store&.connected?
      render json: { error: "Store not found or not connected" }, status: :unauthorized
    end
  end
end
