# frozen_string_literal: true

# RequestLog model - logs API requests for debugging and analytics
#
# Tracks questions asked, queries generated, and responses returned.
# Useful for debugging and understanding usage patterns.
#
class RequestLog < ApplicationRecord
  belongs_to :store

  # Validations
  validates :question, presence: true

  # Scopes
  scope :recent, -> { order(created_at: :desc).limit(100) }
  scope :successful, -> { where(success: true) }
  scope :failed, -> { where(success: false) }

  # Class methods
  class << self
    def log_request(store:, question:, conversation_id: nil)
      create!(
        store: store,
        question: question,
        conversation_id: conversation_id,
        success: false, # Will be updated on completion
        started_at: Time.current
      )
    end
  end

  # Instance methods
  def complete!(response:, query: nil, success: true)
    update!(
      response: response,
      query_used: query,
      success: success,
      completed_at: Time.current,
      duration_ms: calculate_duration
    )
  end

  def fail!(error_message)
    update!(
      error: error_message,
      success: false,
      completed_at: Time.current,
      duration_ms: calculate_duration
    )
  end

  private

  def calculate_duration
    return nil unless started_at

    ((Time.current - started_at) * 1000).to_i
  end
end
