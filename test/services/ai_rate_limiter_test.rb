# frozen_string_literal: true

require "test_helper"

class AiRateLimiterTest < ActiveSupport::TestCase
  setup { Ai::RateLimiter.reset! }

  test "allows twenty hits then blocks the same IP" do
    20.times { assert Ai::RateLimiter.allow?(ip: "1.2.3.4") }
    refute Ai::RateLimiter.allow?(ip: "1.2.3.4")
    assert Ai::RateLimiter.allow?(ip: "5.6.7.8")
  end

  test "signed-in users also have a per-user cap" do
    20.times { assert Ai::RateLimiter.allow?(ip: "10.0.0.#{_1}", user_id: 9) }
    refute Ai::RateLimiter.allow?(ip: "10.0.0.99", user_id: 9)
  end
end
