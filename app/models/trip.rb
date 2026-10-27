class Trip < ApplicationRecord
  STATUSES = %w[planned want_to_go gone].freeze

  belongs_to :user
  has_many :trip_parks, -> { order(:position, :id) }, dependent: :destroy, inverse_of: :trip
  has_many :parks, through: :trip_parks

  before_validation :normalize_fields

  validates :name, presence: true, length: { maximum: 120 }
  validates :notes, length: { maximum: 4_000 }, allow_blank: true
  validates :status, inclusion: { in: STATUSES }
  validate :date_order

  scope :owned_by, ->(user) { where(user_id: user.id) }
  scope :listed_public, -> { where(listed_public: true) }
  scope :newest_first, -> { order(updated_at: :desc) }

  def self.visible_to(user)
    if user
      where("listed_public = TRUE OR user_id = ?", user.id)
    else
      listed_public
    end
  end

  def as_api_json(viewer: nil, parks: nil)
    payload = {
      id: id,
      name: name,
      notes: notes,
      status: status,
      public: listed_public,
      starts_on: starts_on&.iso8601,
      ends_on: ends_on&.iso8601,
      park_count: trip_parks.size,
      mine: viewer&.id == user_id,
      updated_at: updated_at.iso8601
    }
    payload[:parks] = parks unless parks.nil?
    payload
  end

  private

  def normalize_fields
    self.name = name.to_s.strip
    self.notes = notes.to_s.strip.presence
    self.status = status.to_s.presence || "planned"
  end

  def date_order
    return if starts_on.blank? || ends_on.blank?
    return if ends_on >= starts_on

    errors.add(:ends_on, "cannot be before the start date")
  end
end
