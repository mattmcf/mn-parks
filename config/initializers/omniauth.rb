# frozen_string_literal: true

if ENV["GOOGLE_CLIENT_ID"].present? && ENV["GOOGLE_CLIENT_SECRET"].present?
  Rails.application.config.middleware.use OmniAuth::Builder do
    provider :google_oauth2,
             ENV["GOOGLE_CLIENT_ID"],
             ENV["GOOGLE_CLIENT_SECRET"],
             prompt: "select_account",
             scope: "email,profile",
             redirect_uri: ENV["GOOGLE_OAUTH_REDIRECT_URL"]
  end

  OmniAuth.config.path_prefix = "/api/auth"
  OmniAuth.config.allowed_request_methods = %i[get post]
  OmniAuth.config.silence_get_warning = true
end
