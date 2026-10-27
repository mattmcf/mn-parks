# frozen_string_literal: true

ENV["RAILS_ENV"] ||= "test"
require_relative "../config/environment"
require "rails/test_help"

module ActiveSupport
  class TestCase
    parallelize(workers: :number_of_processors)

    def create_user(email: "matt@example.com", password: "password123")
      User.create!(email: email, password: password, password_confirmation: password)
    end

    def create_park(name: "Itasca State Park", park_type: "state", **attrs)
      Park.create!(
        {
          name: name,
          park_type: park_type,
          source: "test",
          source_id: SecureRandom.hex(8),
          latitude: 47.2,
          longitude: -95.2,
          in_minnesota: true
        }.merge(attrs)
      )
    end
  end
end

class ActionDispatch::IntegrationTest
  include Devise::Test::IntegrationHelpers

  def json_body
    JSON.parse(response.body)
  end
end
