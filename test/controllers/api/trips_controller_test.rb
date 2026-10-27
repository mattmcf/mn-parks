# frozen_string_literal: true

require "test_helper"

class Api::TripsControllerTest < ActionDispatch::IntegrationTest
  setup do
    @owner = create_user(email: "owner@example.com")
    @other = create_user(email: "other@example.com")
    @park = create_park
    @second_park = create_park(name: "Gooseberry Falls State Park")
  end

  test "guest can browse public trips but not create" do
    @owner.trips.create!(name: "Public North Shore", listed_public: true, status: "planned")
    @owner.trips.create!(name: "Private only", listed_public: false, status: "planned")

    get "/api/trips/public", as: :json
    assert_response :success
    names = json_body.fetch("trips").map { |row| row["name"] }
    assert_includes names, "Public North Shore"
    assert_not_includes names, "Private only"
    json_body.fetch("trips").each do |row|
      assert_equal true, row["public"]
      assert_equal false, row["mine"]
      assert_nil row["parks"]
    end

    post "/api/trips", params: { name: "Nope" }, as: :json
    assert_response :unauthorized
  end

  test "guest can open a public trip and is 404 on a private one" do
    public_trip = @owner.trips.create!(name: "Public", listed_public: true, notes: "Bring bug spray")
    public_trip.trip_parks.create!(park: @park, position: 1)
    private_trip = @owner.trips.create!(name: "Private", listed_public: false)

    get "/api/trips/#{public_trip.id}", as: :json
    assert_response :success
    trip = json_body.fetch("trip")
    assert_equal "Public", trip["name"]
    assert_equal true, trip["public"]
    assert_equal false, trip["mine"]
    assert_equal 1, trip["park_count"]
    assert_equal @park.name, trip["parks"].first["name"]
    assert_not trip.key?("email")

    get "/api/trips/#{private_trip.id}", as: :json
    assert_response :not_found
    assert_equal "That trip list was not found.", json_body["error"]
  end

  test "owner creates, edits, and lists their own trips including private" do
    sign_in @owner

    post "/api/trips", params: {
      name: "  North Shore weekend  ",
      notes: "Waterfalls",
      status: "planned",
      public: false,
      starts_on: "2026-07-04",
      ends_on: "2026-07-06"
    }, as: :json
    assert_response :created
    trip = json_body.fetch("trip")
    assert_equal "North Shore weekend", trip["name"]
    assert_equal false, trip["public"]
    assert_equal true, trip["mine"]
    assert_equal "planned", trip["status"]
    assert_equal "2026-07-04", trip["starts_on"]
    id = trip["id"]

    get "/api/trips", as: :json
    assert_response :success
    assert_equal [ "North Shore weekend" ], json_body.fetch("trips").map { |row| row["name"] }

    patch "/api/trips/#{id}", params: { public: true, status: "want_to_go" }, as: :json
    assert_response :success
    assert_equal true, json_body.dig("trip", "public")
    assert_equal "want_to_go", json_body.dig("trip", "status")

    get "/api/trips/public", as: :json
    assert_includes json_body.fetch("trips").map { |row| row["id"] }, id
  end

  test "owner can add and remove parks; duplicate add is idempotent" do
    sign_in @owner
    trip = @owner.trips.create!(name: "Arrowhead", listed_public: false)

    post "/api/trips/#{trip.id}/parks", params: { park_id: @park.id }, as: :json
    assert_response :created
    assert_equal 1, json_body.dig("trip", "park_count")
    assert_equal @park.id, json_body.dig("trip", "parks", 0, "id")

    post "/api/trips/#{trip.id}/parks", params: { park_id: @park.id }, as: :json
    assert_response :success
    assert_equal 1, json_body.dig("trip", "park_count")

    post "/api/trips/#{trip.id}/parks", params: { park_id: @second_park.id }, as: :json
    assert_response :created
    assert_equal 2, json_body.dig("trip", "park_count")

    delete "/api/trips/#{trip.id}/parks/#{@park.id}", as: :json
    assert_response :success
    assert_equal [ @second_park.id ], json_body.dig("trip", "parks").map { |row| row["id"] }
  end

  test "other users cannot edit or add parks to someone else's list" do
    trip = @owner.trips.create!(name: "Public", listed_public: true)
    sign_in @other

    patch "/api/trips/#{trip.id}", params: { name: "Hijacked" }, as: :json
    assert_response :not_found
    assert_equal "Public", trip.reload.name

    post "/api/trips/#{trip.id}/parks", params: { park_id: @park.id }, as: :json
    assert_response :not_found
    assert_equal 0, trip.trip_parks.count
  end

  test "owner can open a private list and delete it" do
    sign_in @owner
    trip = @owner.trips.create!(name: "Secret", listed_public: false)

    get "/api/trips/#{trip.id}", as: :json
    assert_response :success
    assert_equal true, json_body.dig("trip", "mine")
    assert_equal false, json_body.dig("trip", "public")

    delete "/api/trips/#{trip.id}", as: :json
    assert_response :no_content
    assert_nil Trip.find_by(id: trip.id)
  end

  test "rejects an unknown status and inverted dates" do
    sign_in @owner

    post "/api/trips", params: { name: "Bad status", status: "camping" }, as: :json
    assert_response :unprocessable_content

    post "/api/trips", params: {
      name: "Backwards",
      starts_on: "2026-08-10",
      ends_on: "2026-08-01"
    }, as: :json
    assert_response :unprocessable_content
    assert_match(/cannot be before the start date/, json_body["error"])
  end

  test "my trips index requires login" do
    get "/api/trips", as: :json
    assert_response :unauthorized
  end
end
