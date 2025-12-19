# frozen_string_literal: true

class HealthController < ApplicationController
  def show
    render json: {
      status: "healthy",
      service: "shopify-ai-analytics-api",
      version: "1.0.0",
      timestamp: Time.current.iso8601
    }
  end
end
