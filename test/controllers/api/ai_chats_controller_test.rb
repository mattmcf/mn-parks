# frozen_string_literal: true

require "test_helper"

class Api::AiChatsControllerTest < ActionDispatch::IntegrationTest
  setup do
    Ai::RateLimiter.reset!
    @itasca = create_park(
      name: "Itasca State Park",
      park_type: "state",
      latitude: 47.250031,
      longitude: -95.212237,
      highlights: "Headwaters of the Mississippi.",
      amenities: [ "camping", "fishing", "beach" ],
      activities: [ "camping", "fishing" ],
      camping_score: 3.6,
      camping: { "kind" => "official_inventory", "campsite_count" => 246, "snippet" => "246 official DNR camping units." }
    )
    @voyageurs = create_park(
      name: "Voyageurs National Park",
      park_type: "national",
      latitude: 48.483706,
      longitude: -92.838291,
      amenities: [ "camping", "hiking", "fishing" ],
      dark_sky_certified: true,
      dark_sky: { "category" => "park", "category_label" => "International Dark Sky Park", "designated" => "2020" }
    )
    @bwca = create_park(
      name: "Boundary Waters Canoe Area Wilderness",
      park_type: "wilderness",
      latitude: 48.028871,
      longitude: -91.388043,
      amenities: [ "canoeing", "camping", "fishing" ],
      dark_sky_certified: true,
      dark_sky: { "category" => "sanctuary", "category_label" => "International Dark Sky Sanctuary" }
    )
    @belle = create_park(
      name: "Belle Prairie County Park",
      park_type: "county",
      latitude: 46.016,
      longitude: -94.348,
      amenities: [ "picnic", "hiking", "fishing" ]
    )
  end

  test "guest can plan from park JSON without a paid key" do
    post "/api/ai/chat", params: { messages: [ { role: "user", content: "dark sky" } ] }, as: :json
    assert_response :success
    assert_includes json_body.fetch("message"), "Voyageurs National Park"
    ids = json_body.fetch("parks").map { |row| row["id"] }
    assert_includes ids, @voyageurs.id
    assert_includes ids, @bwca.id
    refute_includes ids, @itasca.id
    trip = json_body.fetch("proposed_trip")
    assert_equal "planned", trip["status"]
    assert_equal "Dark Sky parks", trip["name"]
    assert_equal ids, trip["park_ids"]
  end

  test "Itasca camping cites score and guest still sees a proposed trip" do
    post "/api/ai/chat", params: { messages: [ { role: "user", content: "Itasca camping" } ] }, as: :json
    assert_response :success
    parks = json_body.fetch("parks")
    assert_equal [ @itasca.id ], parks.map { |row| row["id"] }
    assert_includes json_body.fetch("message"), "camping score 3.6"
    assert json_body["proposed_trip"]
  end

  test "county fishing and picnic does not leak state parks" do
    post "/api/ai/chat",
         params: { messages: [ { role: "user", content: "county parks with fishing and a picnic" } ] },
         as: :json
    assert_response :success
    names = json_body.fetch("parks").map { |row| row["name"] }
    assert_includes names, "Belle Prairie County Park"
    refute_includes names, "Itasca State Park"
  end

  test "garbage prompt is an honest miss, not invented parks" do
    post "/api/ai/chat", params: { messages: [ { role: "user", content: "asdfgh qwerty zxcvbn" } ] }, as: :json
    assert_response :success
    assert_equal Ai::Planner::NO_MATCH, json_body["message"]
    assert_equal [], json_body["parks"]
    assert_nil json_body["proposed_trip"]
  end

  test "rate limit is 20 posts per 10 minutes per IP" do
    20.times do
      post "/api/ai/chat", params: { messages: [ { role: "user", content: "dark sky" } ] }, as: :json
      assert_response :success
    end
    post "/api/ai/chat", params: { messages: [ { role: "user", content: "dark sky" } ] }, as: :json
    assert_response :too_many_requests
    assert_match(/Too many/, json_body["error"])
  end

  test "signed-in user is serialized the same and save stays on trip APIs" do
    user = create_user
    sign_in user
    post "/api/ai/chat", params: { messages: [ { role: "user", content: "Itasca camping" } ] }, as: :json
    assert_response :success
    park_ids = json_body.fetch("proposed_trip").fetch("park_ids")

    post "/api/trips", params: {
      name: json_body.dig("proposed_trip", "name"),
      notes: json_body.dig("proposed_trip", "notes"),
      status: "planned",
      public: false
    }, as: :json
    assert_response :created
    trip_id = json_body.dig("trip", "id")
    assert_equal false, json_body.dig("trip", "public")

    post "/api/trips/#{trip_id}/parks", params: { park_id: park_ids.first }, as: :json
    assert_response :created
    assert_equal park_ids.first, json_body.dig("trip", "parks", 0, "id")
  end
end
