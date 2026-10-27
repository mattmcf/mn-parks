# frozen_string_literal: true

require "test_helper"

class TripTest < ActiveSupport::TestCase
  setup do
    @user = create_user
  end

  test "requires a name and a known status" do
    trip = @user.trips.new(name: "", status: "roadtrip")
    assert_not trip.valid?
    assert_includes trip.errors[:name], "can't be blank"
    assert_includes trip.errors[:status], "is not included in the list"
  end

  test "rejects an end date before the start date" do
    trip = @user.trips.new(name: "North Shore", starts_on: "2026-07-06", ends_on: "2026-07-04")
    assert_not trip.valid?
    assert_includes trip.errors[:ends_on], "cannot be before the start date"
  end

  test "visible_to includes public lists and the owner's private lists" do
    owner = @user
    other = create_user(email: "other@example.com")
    public_trip = owner.trips.create!(name: "BWCA", status: "planned", listed_public: true)
    private_trip = owner.trips.create!(name: "Secret", status: "want_to_go", listed_public: false)
    other.trips.create!(name: "Hidden", status: "gone", listed_public: false)

    guest_ids = Trip.visible_to(nil).pluck(:id)
    assert_includes guest_ids, public_trip.id
    assert_not_includes guest_ids, private_trip.id

    owner_ids = Trip.visible_to(owner).pluck(:id)
    assert_includes owner_ids, public_trip.id
    assert_includes owner_ids, private_trip.id
    assert_equal 2, owner_ids.size
  end

  test "as_api_json never includes the owner email and maps listed_public to public" do
    trip = @user.trips.create!(name: "North Shore", notes: "Waterfalls", listed_public: false)
    json = trip.as_api_json(viewer: @user)
    assert_equal false, json[:public]
    assert_equal true, json[:mine]
    assert_nil json[:parks]
    assert_not json.key?(:email)
    assert_equal "North Shore", json[:name]
  end
end
