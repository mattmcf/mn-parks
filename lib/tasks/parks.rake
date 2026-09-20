# frozen_string_literal: true

namespace :parks do
  desc "Load parks from db/data/parks.json (rebuild JSON with scripts/build_parks_json.py first)"
  task ingest: :environment do
    load Rails.root.join("db/seeds.rb")
  end
end
