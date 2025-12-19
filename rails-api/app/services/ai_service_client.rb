# frozen_string_literal: true

# AiServiceClient - HTTP client for the Python AI service
#
# Handles communication with the FastAPI AI service that processes
# natural language questions and generates analytics responses.
#
class AiServiceClient
  class ServiceError < StandardError; end
  class TimeoutError < ServiceError; end
  class ConnectionError < ServiceError; end

  AI_SERVICE_URL = ENV.fetch("PYTHON_AI_SERVICE_URL", "http://localhost:8000")
  TIMEOUT_SECONDS = 60

  class << self
    # Analyze a question using the AI service
    #
    # @param store_id [String] The Shopify store domain
    # @param question [String] The natural language question
    # @param access_token [String] The Shopify API access token
    # @param conversation_id [String, nil] Optional conversation ID for follow-ups
    # @return [Hash] The AI service response
    #
    def analyze(store_id:, question:, access_token:, conversation_id: nil)
      payload = {
        store_id: store_id,
        question: question,
        access_token: access_token,
        conversation_id: conversation_id
      }.compact

      response = make_request("/api/v1/analyze", payload)

      {
        answer: response["answer"],
        confidence: response["confidence"],
        query_used: response["query_used"],
        raw_data: response["raw_data"],
        conversation_id: response["conversation_id"],
        error: response["error"]
      }
    end

    # Check the health of the AI service
    #
    # @return [Hash] Health status
    #
    def health_check
      response = HTTParty.get(
        "#{AI_SERVICE_URL}/health",
        timeout: 5
      )

      {
        healthy: response.success?,
        status: response.parsed_response
      }
    rescue StandardError => e
      { healthy: false, error: e.message }
    end

    private

    def make_request(endpoint, payload)
      url = "#{AI_SERVICE_URL}#{endpoint}"

      Rails.logger.info("AI Service request to #{url}")

      response = HTTParty.post(
        url,
        body: payload.to_json,
        headers: {
          "Content-Type" => "application/json",
          "Accept" => "application/json"
        },
        timeout: TIMEOUT_SECONDS
      )

      handle_response(response)
    rescue Net::OpenTimeout, Net::ReadTimeout => e
      Rails.logger.error("AI Service timeout: #{e.message}")
      raise TimeoutError, "AI service request timed out"
    rescue Errno::ECONNREFUSED, SocketError => e
      Rails.logger.error("AI Service connection error: #{e.message}")
      raise ConnectionError, "Could not connect to AI service"
    rescue StandardError => e
      Rails.logger.error("AI Service error: #{e.message}")
      raise ServiceError, e.message
    end

    def handle_response(response)
      case response.code
      when 200..299
        response.parsed_response
      when 400..499
        error_message = response.parsed_response&.dig("detail") || "Bad request"
        raise ServiceError, "Client error: #{error_message}"
      when 500..599
        raise ServiceError, "AI service internal error"
      else
        raise ServiceError, "Unexpected response: #{response.code}"
      end
    end
  end
end
