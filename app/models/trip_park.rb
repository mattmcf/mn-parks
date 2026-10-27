class TripPark < ApplicationRecord
  belongs_to :trip, touch: true
  belongs_to :park

  validates :park_id, uniqueness: { scope: :trip_id }
  validates :position, numericality: { only_integer: true, greater_than_or_equal_to: 0 }
end
