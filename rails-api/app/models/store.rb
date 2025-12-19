# frozen_string_literal: true

# Store model - represents a connected Shopify store
#
# Stores OAuth credentials and metadata for each connected store.
# Access tokens are encrypted at rest for security.
#
class Store < ApplicationRecord
  # Encrypt the access token
  attr_encrypted :access_token,
                 key: ENV.fetch("ENCRYPTION_KEY", "a" * 32),
                 algorithm: "aes-256-gcm"

  # Validations
  validates :shop_domain, presence: true, uniqueness: true
  validates :encrypted_access_token, presence: true

  # Associations
  has_many :request_logs, dependent: :destroy

  # Scopes
  scope :active, -> { where(active: true) }

  # Callbacks
  before_validation :normalize_shop_domain

  # Class methods
  class << self
    def find_by_domain(domain)
      normalized = normalize_domain(domain)
      find_by(shop_domain: normalized)
    end

    def normalize_domain(domain)
      domain.to_s
            .downcase
            .gsub(%r{^https?://}, "")
            .gsub(%r{/$}, "")
            .then { |d| d.include?(".myshopify.com") ? d : "#{d}.myshopify.com" }
    end
  end

  # Instance methods
  def api_url
    "https://#{shop_domain}/admin/api/#{api_version}"
  end

  def graphql_url
    "#{api_url}/graphql.json"
  end

  def api_version
    ENV.fetch("SHOPIFY_API_VERSION", "2024-01")
  end

  def connected?
    access_token.present? && active?
  end

  def disconnect!
    update!(access_token: nil, active: false)
  end

  private

  def normalize_shop_domain
    self.shop_domain = self.class.normalize_domain(shop_domain) if shop_domain.present?
  end
end
