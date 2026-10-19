# frozen_string_literal: true

# Split Cache-Control for the Vite SPA that Rails serves from public/.
#
# Rails 8 `config.public_file_server.headers` is one hash applied to every file
# under public/. A 1-year max-age (correct for hashed JS/CSS) therefore also
# far-cached index.html, so browsers kept a stale SPA shell after deploys until
# a shift-reload. This middleware wraps ActionDispatch::Static and sets:
#
# - HTML (`/`, `/index.html`, other HTML documents): short max-age
# - hashed `/spa-assets/*`: long immutable cache (the filename is the hash)
# - `/api` and `/up`: leave Rails' own headers alone (never far-cached)
class SpaCacheHeaders
  HTML_CACHE = "public, max-age=60, must-revalidate"
  ASSET_CACHE = "public, max-age=31536000, immutable"

  def initialize(app)
    @app = app
  end

  def call(env)
    status, headers, body = @app.call(env)
    return [ status, headers, body ] unless status == 200

    path = env["PATH_INFO"].to_s
    return [ status, headers, body ] if skip?(path)

    headers = headers.dup
    if hashed_asset?(path)
      set_cache(headers, ASSET_CACHE)
    elsif html?(path, headers)
      set_cache(headers, HTML_CACHE)
    end

    [ status, headers, body ]
  end

  private

  def skip?(path)
    path == "/up" || path == "/api" || path == "/rails" ||
      path.start_with?("/api/", "/rails/")
  end

  def hashed_asset?(path)
    path.start_with?("/spa-assets/")
  end

  def html?(path, headers)
    return true if path == "/" || path == "/index.html" || path.end_with?(".html")

    content_type = headers["content-type"] || headers["Content-Type"]
    content_type.to_s.downcase.include?("text/html")
  end

  def set_cache(headers, value)
    headers.delete("Cache-Control")
    headers.delete("cache-control")
    headers["cache-control"] = value
  end
end
