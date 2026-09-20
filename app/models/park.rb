class Park < ApplicationRecord
  TYPES = %w[national state regional county].freeze
  SHIPPED_PATH = Rails.root.join("db/data/parks.json")
  DARK_SKY_PATH = Rails.root.join("db/data/dark_sky.json")
  REVIEWS_PATH = Rails.root.join("db/data/park_reviews.json")

  has_many :park_user_states, dependent: :destroy

  def self.shipped_payload
    JSON.parse(SHIPPED_PATH.read)
  end

  def self.intel_payload(path)
    return {} unless path.exist?

    JSON.parse(path.read)
  rescue JSON::ParserError
    {}
  end

  # Inventory source of truth is the committed JSON files. Remote GIS / DarkSky /
  # NPS campgrounds are only contacted by rake refresh tasks, never by boot.
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
          retrieved_at: row["retrieved_at"],
          dark_sky_certified: false,
          dark_sky: {},
          camping_score: nil,
          camping: {}
        )
        park.save!
      end
      apply_dark_sky!
      apply_reviews!
    end
    payload
  end

  def self.apply_dark_sky!
    payload = intel_payload(DARK_SKY_PATH)
    (payload["places"] || []).each do |row|
      park = find_by(source: row["matched_source"], source_id: row["matched_source_id"].to_s)
      next unless park

      park.update!(
        dark_sky_certified: true,
        dark_sky: {
          "category" => row["category"],
          "category_label" => row["category_label"],
          "designated" => row["designated"],
          "url" => row["darksky_url"],
          "retrieved_at" => payload["retrieved_at"]
        }.compact
      )
    end
  end

  def self.apply_reviews!
    payload = intel_payload(REVIEWS_PATH)
    (payload["reviews"] || []).each do |row|
      park = find_by(source: row["source"], source_id: row["source_id"].to_s)
      next unless park

      park.update!(
        camping_score: row["camping_score"],
        camping: {
          "kind" => row["score_kind"] || "official_inventory",
          "campsite_count" => row["campsite_count"],
          "review_count" => row["review_count"],
          "snippet" => row["snippet"],
          "url" => row["url"],
          "inventory_source" => row["inventory_source"],
          "retrieved_at" => payload["retrieved_at"]
        }.compact
      )
    end
  end

  validates :name, :park_type, :source, :source_id, :latitude, :longitude, presence: true
  validates :park_type, inclusion: { in: TYPES }

  scope :in_state, -> { where(in_minnesota: true) }

  def as_api_json(user: nil, state: nil)
    state ||= park_user_states.find { |s| s.user_id == user&.id } if user
    dark = dark_sky_certified ? (dark_sky.presence || {}) : nil
    camp = camping.presence
    camp = nil if camp.blank?
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
      dark_sky_certified: dark_sky_certified,
      dark_sky: dark && {
        category: dark["category"],
        category_label: dark["category_label"],
        designated: dark["designated"],
        url: dark["url"]
      }.compact,
      camping_score: camping_score && camping_score.to_f.round(1),
      camping: camp && {
        kind: camp["kind"],
        campsite_count: camp["campsite_count"],
        review_count: camp["review_count"],
        snippet: camp["snippet"],
        url: camp["url"]
      }.compact,
      favorited: user ? state&.favorited == true : nil,
      visited: user ? state&.visited == true : nil
    }
  end
end
