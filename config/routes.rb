Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check

  devise_for :users, skip: :all

  namespace :api, defaults: { format: :json } do
    get "csrf", to: "sessions#csrf"
    get "me", to: "sessions#show"
    post "signup", to: "registrations#create"
    post "login", to: "sessions#create"
    delete "logout", to: "sessions#destroy"

    get "auth/google_oauth2/callback", to: "omniauth_callbacks#google_oauth2"
    post "auth/google_oauth2/callback", to: "omniauth_callbacks#google_oauth2"
    get "auth/failure", to: "omniauth_callbacks#failure"

    resources :parks, only: [ :index, :show ] do
      get :random, on: :collection
      patch :user_state, on: :member
    end

    get "trips/public", to: "trips#public_index"
    resources :trips, only: [ :index, :show, :create, :update, :destroy ] do
      resources :parks, only: [ :create, :destroy ], controller: "trip_parks"
    end

    post "ai/chat", to: "ai_chats#create"
  end

  # Vite SPA in production (bin/install-spa copies web/dist → public/).
  root "spa#index"
  get "*path", to: "spa#index", constraints: ->(req) {
    !req.path.start_with?("/api", "/up", "/rails", "/assets", "/spa-assets")
  }
end
