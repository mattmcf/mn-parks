# frozen_string_literal: true

namespace :parks do
  desc "Fetch official GIS/API sources, rewrite db/data/parks.json, then load it into Postgres"
  task refresh: :environment do
    ParksJsonBuilder.refresh!
    Rake::Task["parks:ingest"].invoke
  end

  desc "Load the shipped db/data/parks.json into Postgres (offline; no DNR/NPS/Met Council calls)"
  task ingest: :environment do
    payload = Park.ingest_shipped!
    counts = payload["counts"] || Park.in_state.group(:park_type).count
    puts "Loaded #{Park.count} parks from #{Park::SHIPPED_PATH.relative_path_from(Rails.root)} (#{counts})"
  end
end

# Rebuilds the committed park inventory. Runtime map/API never call this.
module ParksJsonBuilder
  module_function

  def refresh!
    python = python!
    ensure_deps!(python)
    script = Rails.root.join("scripts/build_parks_json.py")
    puts "Fetching MN DNR, NPS, Met Council, and MetroGIS county parks…"
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
