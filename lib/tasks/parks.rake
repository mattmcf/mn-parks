# frozen_string_literal: true

namespace :parks do
  desc "Fetch official sources, rewrite parks/dark-sky/reviews JSON, then load Postgres"
  task refresh: :environment do
    ParksJsonBuilder.refresh!
    DarkSkyJsonBuilder.refresh!
    ParkReviewsJsonBuilder.refresh!
    Rake::Task["parks:ingest"].invoke
  end

  desc "Fetch DarkSky International certified places, rewrite db/data/dark_sky.json, ingest"
  task refresh_dark_sky: :environment do
    DarkSkyJsonBuilder.refresh!
    Rake::Task["parks:ingest"].invoke
  end

  desc "Fetch official campground inventories, rewrite db/data/park_reviews.json, ingest"
  task refresh_reviews: :environment do
    ParkReviewsJsonBuilder.refresh!
    Rake::Task["parks:ingest"].invoke
  end

  desc "Load shipped JSON artifacts into Postgres (offline; no DarkSky/DNR/NPS/review-site calls)"
  task ingest: :environment do
    payload = Park.ingest_shipped!
    counts = payload["counts"] || Park.in_state.group(:park_type).count
    dark = Park.in_state.where(dark_sky_certified: true).count
    scored = Park.in_state.where.not(camping_score: nil).count
    puts "Loaded #{Park.count} parks from #{Park::SHIPPED_PATH.relative_path_from(Rails.root)} (#{counts})"
    puts "Dark Sky certified: #{dark}. Parks with a camping score: #{scored}."
  end
end

# Rebuilds the committed park inventory. Runtime map/API never call this.
module ParksJsonBuilder
  module_function

  def refresh!
    python = python!
    ensure_deps!(python)
    script = Rails.root.join("scripts/build_parks_json.py")
    puts "Fetching MN DNR, NPS, Met Council, MetroGIS, and NWPS wilderness…"
    abort "Park JSON rebuild failed." unless system(python, script.to_s)
    abort "Expected #{Park::SHIPPED_PATH} after rebuild." unless Park::SHIPPED_PATH.exist?
  end

  def python!
    %w[python3 python].each do |cmd|
      path = `command -v #{cmd} 2>/dev/null`.strip
      return path if path.present?
    end
    abort "python3 is required for parks:refresh."
  end

  def ensure_deps!(python)
    ok = system(
      python, "-c", "import shapefile, pyproj, shapely",
      out: File::NULL, err: File::NULL
    )
    return if ok

    req = Rails.root.join("scripts/requirements.txt")
    puts "Installing Python ingest dependencies from #{req.relative_path_from(Rails.root)}…"
    abort "pip install failed." unless system(python, "-m", "pip", "install", "-r", req.to_s)
  end
end

module DarkSkyJsonBuilder
  module_function

  def refresh!
    python = ParksJsonBuilder.python!
    script = Rails.root.join("scripts/build_dark_sky_json.py")
    puts "Fetching DarkSky International certified places…"
    abort "Dark Sky JSON rebuild failed." unless system(python, script.to_s)
    abort "Expected #{Park::DARK_SKY_PATH} after rebuild." unless Park::DARK_SKY_PATH.exist?
  end
end

module ParkReviewsJsonBuilder
  module_function

  def refresh!
    python = ParksJsonBuilder.python!
    script = Rails.root.join("scripts/build_park_reviews.py")
    puts "Fetching MN DNR camping units and NPS campgrounds…"
    abort "Park reviews JSON rebuild failed." unless system(python, script.to_s)
    abort "Expected #{Park::REVIEWS_PATH} after rebuild." unless Park::REVIEWS_PATH.exist?
  end
end
