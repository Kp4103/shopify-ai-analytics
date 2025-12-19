Rails.application.routes.draw do
  # Health check
  get "health", to: "health#show"

  # Shopify OAuth routes
  get "auth/shopify", to: "auth#shopify"
  get "auth/shopify/callback", to: "auth#callback"

  # API namespace
  namespace :api do
    namespace :v1 do
      # Questions endpoint - main analytics interface
      post "questions", to: "questions#create"

      # Store management
      resources :stores, only: [:show, :index] do
        member do
          get :test_connection
        end
      end

      # Conversation history (optional)
      resources :conversations, only: [:show, :destroy]
    end
  end

  # Root route
  root to: "health#show"
end
