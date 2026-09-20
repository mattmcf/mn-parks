class Park < ApplicationRecord
  TYPES = %w[national state regional county].freeze

  has_many :park_user_states, dependent: :destroy

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
