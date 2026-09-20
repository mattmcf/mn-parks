# frozen_string_literal: true

payload = JSON.parse(Rails.root.join("db/data/parks.json").read)
parks = payload.fetch("parks")

Park.transaction do
  parks.each do |row|
    park = Park.find_or_initialize_by(source: row["source"], source_id: row["source_id"].to_s)
    park.assign_attributes(
      name: row["name"],
      park_type: row["park_type"],
      managing_agency: row["managing_agency"],
      source_url: row["source_url"],
      latitude: row["latitude"],
      longitude: row["longitude"],
      highlights: row["highlights"].presence,
      amenities: row["amenities"] || [],
      activities: row["activities"] || [],
      in_minnesota: row.fetch("in_minnesota", true),
      retrieved_at: row["retrieved_at"]
    )
    park.save!
  end
end

puts "Seeded #{Park.count} parks (#{payload.dig("counts")})"
