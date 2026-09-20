# frozen_string_literal: true

# Parks come from the committed static asset. `rails db:seed` does not hit
# DNR, NPS, or Met Council — run `bin/rake parks:refresh` to rebuild the file.
payload = Park.ingest_shipped!
puts "Seeded #{Park.count} parks (#{payload["counts"]})"
