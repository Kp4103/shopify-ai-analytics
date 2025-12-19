# frozen_string_literal: true

module Api
  module V1
    # QuestionsController - Main endpoint for natural language analytics
    #
    # POST /api/v1/questions
    # {
    #   "store_id": "example-store.myshopify.com",
    #   "question": "What were my top 5 selling products last week?",
    #   "conversation_id": "optional-uuid"
    # }
    #
    class QuestionsController < BaseController
      def create
        # Validate request
        unless question_params[:question].present?
          return render json: { error: "Missing question parameter" }, status: :bad_request
        end

        # Log the request
        request_log = RequestLog.log_request(
          store: @current_store,
          question: question_params[:question],
          conversation_id: question_params[:conversation_id]
        )

        begin
          # Forward to Python AI service
          ai_response = AiServiceClient.analyze(
            store_id: @current_store.shop_domain,
            question: question_params[:question],
            access_token: @current_store.access_token,
            conversation_id: question_params[:conversation_id]
          )

          # Update request log with response
          request_log.complete!(
            response: ai_response[:answer],
            query: ai_response[:query_used],
            success: ai_response[:error].blank?
          )

          render json: format_response(ai_response)

        rescue AiServiceClient::ServiceError => e
          request_log.fail!(e.message)
          render json: {
            error: "AI service error",
            message: e.message
          }, status: :service_unavailable

        rescue StandardError => e
          request_log.fail!(e.message)
          Rails.logger.error("Question processing error: #{e.message}")
          render json: {
            error: "Processing error",
            message: "Failed to process your question. Please try again."
          }, status: :internal_server_error
        end
      end

      private

      def question_params
        params.permit(:store_id, :question, :conversation_id)
      end

      def format_response(ai_response)
        {
          answer: ai_response[:answer],
          confidence: ai_response[:confidence] || "medium",
          query_used: ai_response[:query_used],
          conversation_id: ai_response[:conversation_id],
          timestamp: Time.current.iso8601
        }.compact
      end
    end
  end
end
