# frozen_string_literal: true

# Serves the Vite production build (public/index.html) for the public site.
# APIs stay under /api. ActionDispatch::Static usually handles GET / first;
# this is the fallback when the request reaches Rails.
class SpaController < ApplicationController
  def index
    path = Rails.public_path.join("index.html")
    return head :not_found unless path.exist?

    send_file path, type: "text/html; charset=utf-8", disposition: "inline"
  end
end
