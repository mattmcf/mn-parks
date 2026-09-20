# frozen_string_literal: true

Rails.application.config.middleware.insert_before 0, Rack::Cors do
  origins = [
    ENV.fetch("FRONTEND_ORIGIN", "http://127.0.0.1:4174"),
    "http://127.0.0.1:4174",
    "http://localhost:4174"
  ].uniq

  allow do
    origins(*origins)
    resource "*",
             headers: :any,
             methods: %i[get post put patch delete options head],
             credentials: true
  end
end
