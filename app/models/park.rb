class Park < ApplicationRecord
  TYPES = %w[national state regional county].freeze
  SHIPPED_PATH = Rails.root.join("db/data/parks.json")

  has_many :park_user_states, dependent: :destroy

  def self.shipped_payload
    JSON.parse(SHIPPED_PATH.read)
  end

  # Inventory source of truth is the committed JSON file. Remote GIS is only
  # contacted by `rake parks:refresh`, never by rails server / Vite boot.
  def self.ingest_shipped!
    payload = shipped_payload
    parks = payload.fetch("parks")
    transaction do
      parks.each do |row|
        park = find_or_initialize_by(source: row["source"], source_id: row["source_id"].to_s)
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
    payload
  end

  validates :name, :park_type, :source, :source_id, :latitude, :longitude, presence: true
  validates :park_type, inclusion: { in: TYPES }

  scope :in_state, -> { where(in_minnesota: true) }

  def as_api_json(user: nil, state: nil)
    state ||= park_user_states.find { |s| s.user_id == user&.id } if user
    {
      id: id,
      name: name,
      park_type: park_type,
      managing_agency: managing_agency,
      source: source,
      source_id: source_id,
      source_url: source_url,
      latitude: latitude.to_f,
      longitude: longitude.to_f,
      highlights: highlights,
      amenities: amenities || [],
      activities: activities || [],
      favorited: user ? state&.favorited == true : nil,
      visited: user ? state&.visited == true : nil
    }
  end
end
