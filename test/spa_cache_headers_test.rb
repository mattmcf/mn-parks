# frozen_string_literal: true

# Standalone (no Rails): ruby test/spa_cache_headers_test.rb
require "minitest/autorun"
require_relative "../lib/spa_cache_headers"

class SpaCacheHeadersTest < Minitest::Test
  def test_root_html_is_short_cache
    _, headers, = middleware(html_app).call(env("/"))
    assert_equal SpaCacheHeaders::HTML_CACHE, headers["cache-control"]
  end

  def test_index_html_is_short_cache
    _, headers, = middleware(html_app).call(env("/index.html"))
    assert_equal SpaCacheHeaders::HTML_CACHE, headers["cache-control"]
  end

  def test_client_route_html_is_short_cache
    _, headers, = middleware(html_app).call(env("/some/spa/path"))
    assert_equal SpaCacheHeaders::HTML_CACHE, headers["cache-control"]
  end

  def test_hashed_spa_assets_are_immutable
    app = ->(_env) { [ 200, { "content-type" => "text/javascript" }, [ "js" ] ] }
    _, headers, = middleware(app).call(env("/spa-assets/index-Ras6ReEC.js"))
    assert_equal SpaCacheHeaders::ASSET_CACHE, headers["cache-control"]
    assert_match(/immutable/, headers["cache-control"])
    assert_match(/max-age=31536000/, headers["cache-control"])
  end

  def test_does_not_far_cache_api
    app = ->(_env) { [ 200, { "content-type" => "application/json", "cache-control" => "max-age=0, private, must-revalidate" }, [ "{}" ] ] }
    _, headers, = middleware(app).call(env("/api/parks"))
    assert_equal "max-age=0, private, must-revalidate", headers["cache-control"]
  end

  def test_does_not_far_cache_up
    app = ->(_env) { [ 200, { "content-type" => "text/html; charset=utf-8", "cache-control" => "max-age=0, private, must-revalidate" }, [ "ok" ] ] }
    _, headers, = middleware(app).call(env("/up"))
    assert_equal "max-age=0, private, must-revalidate", headers["cache-control"]
  end

  def test_overrides_one_year_public_file_server_header_on_html
    app = ->(_env) { [ 200, { "content-type" => "text/html", "cache-control" => "public, max-age=31556952" }, [ "<html>" ] ] }
    _, headers, = middleware(app).call(env("/"))
    assert_equal SpaCacheHeaders::HTML_CACHE, headers["cache-control"]
  end

  def test_skips_non_success
    app = ->(_env) { [ 301, { "content-type" => "text/html", "cache-control" => "no-cache" }, [ "" ] ] }
    _, headers, = middleware(app).call(env("/"))
    assert_equal "no-cache", headers["cache-control"]
  end

  private

  def middleware(app)
    SpaCacheHeaders.new(app)
  end

  def html_app
    ->(_env) { [ 200, { "content-type" => "text/html; charset=utf-8", "cache-control" => "public, max-age=31556952" }, [ "<html>" ] ] }
  end

  def env(path)
    { "PATH_INFO" => path, "REQUEST_METHOD" => "GET" }
  end
end
