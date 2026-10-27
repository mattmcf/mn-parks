# frozen_string_literal: true

require "test_helper"

class AiPlannerTest < ActiveSupport::TestCase
  setup do
    @parks = JSON.parse(Rails.root.join("test/fixtures/files/ai_planner_parks.json").read)
  end

  test "provider defaults to mock so Hobby needs no paid key" do
    previous = ENV["AI_LLM_PROVIDER"]
    ENV.delete("AI_LLM_PROVIDER")
    assert_equal "mock", Ai::Planner.provider
    ENV["AI_LLM_PROVIDER"] = "mock"
    assert_equal "mock", Ai::Planner.provider
  ensure
    ENV["AI_LLM_PROVIDER"] = previous
  end

  test "dark sky returns only the two certified parks and proposes a trip" do
    result = plan("dark sky")
    assert_equal [ 2, 3 ], result.park_ids.sort
    assert_includes result.message, "Voyageurs National Park"
    assert_includes result.message, "Boundary Waters Canoe Area Wilderness"
    assert_includes result.message, "Dark Sky"
    refute_includes result.message, "Itasca"
    assert_equal "planned", result.proposed_trip["status"]
    assert_equal "Dark Sky parks", result.proposed_trip["name"]
    assert_equal result.park_ids, result.proposed_trip["park_ids"]
  end

  test "Itasca camping cites official inventory score and units" do
    result = plan("Itasca camping")
    assert_equal [ 1 ], result.park_ids
    assert_includes result.message, "Itasca State Park"
    assert_includes result.message, "camping score 3.6"
    assert_includes result.message, "246 official camping units"
    assert_equal "planned", result.proposed_trip["status"]
    assert_includes result.proposed_trip["name"], "Itasca"
  end

  test "county parks with fishing and a picnic require both amenities" do
    result = plan("county parks with fishing and a picnic")
    names = names_for(result)
    assert_includes names, "Belle Prairie County Park"
    assert_includes names, "Arrowhead Point County Park"
    refute_includes names, "Boulder Lake Conservation Area"
    refute_includes names, "Itasca State Park"
    refute_includes names, "Afton State Park"
  end

  test "garbage input uses the honest no-match copy" do
    result = plan("asdfgh qwerty zxcvbn")
    assert_equal [], result.park_ids
    assert_equal Ai::Planner::NO_MATCH, result.message
    assert_nil result.proposed_trip
  end

  test "no-match for amenities we do not hold together" do
    result = plan("waterfall climbing snowshoeing")
    assert_equal [], result.park_ids
    assert_equal Ai::Planner::NO_MATCH, result.message
  end

  test "North Shore weekend stays on the shore and can suggest a trip" do
    result = plan("a North Shore weekend with hiking and a beach")
    names = names_for(result)
    assert names.any?, result.message
    names.each do |name|
      refute_includes [ "Afton State Park", "Minnehaha Regional Park", "Arrowhead Point County Park" ], name
    end
    assert_equal "planned", result.proposed_trip["status"]
    assert_includes result.proposed_trip["name"], "North Shore"
    refute_includes result.proposed_trip["name"], "Arrowhead Point"
  end

  test "near Duluth uses the gazetteer, not a live geocoder" do
    result = plan("near Duluth")
    names = names_for(result)
    assert_includes names, "Jay Cooke State Park"
    refute_includes names, "Itasca State Park"
    refute_includes names, "Afton State Park"
  end

  test "unknown place asks for a From pin instead of calling Nominatim" do
    result = plan("near Atlantis")
    assert_equal [], result.park_ids
    assert_match(/gazetteer/i, result.message)
    assert_match(/From pin/i, result.message)
    refute_match(/Nominatim|Google|AllTrails/i, result.message)
  end

  test "near me without an origin asks for GPS or a pin" do
    result = plan("parks near me")
    assert_equal [], result.park_ids
    assert_equal Ai::Planner::NEAR_ME_HINT, result.message
  end

  test "near me with origin ranks by straight-line miles" do
    result = plan("parks near me", origin: { latitude: 46.7867, longitude: -92.1005 })
    assert_includes names_for(result), "Jay Cooke State Park"
    refute_includes names_for(result), "Afton State Park"
  end

  test "empty prompt asks him what he wants" do
    result = plan("   ")
    assert_equal Ai::Planner::EMPTY_PROMPT, result.message
    assert_nil result.proposed_trip
  end

  test "does not invent parks that are not in the corpus" do
    result = plan("Yellowstone camping")
    refute_includes names_for(result), "Yellowstone"
    assert result.park_ids.empty? || names_for(result).all? { |name| @parks.any? { |park| park["name"] == name } }
  end

  private

  def plan(content, origin: nil)
    Ai::Planner.plan(
      messages: [ { role: "user", content: content } ],
      origin: origin,
      parks: @parks
    )
  end

  def names_for(result)
    ids = result.park_ids
    @parks.select { |park| ids.include?(park["id"]) }.map { |park| park["name"] }
  end
end
