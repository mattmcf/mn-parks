# frozen_string_literal: true

# Parks come from committed static assets. `rails db:seed` does not hit
# DNR, NPS, Met Council, wilderness GIS, DarkSky, or review sites — run `bin/rake parks:refresh`
# (or parks:refresh_dark_sky / parks:refresh_reviews) to rebuild the files.
payload = Park.ingest_shipped!
puts "Seeded #{Park.count} parks (#{payload["counts"]})"
