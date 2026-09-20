module Api
  # Park inventory is served from Postgres after `db:seed` / `parks:ingest`
  # loaded `db/data/parks.json`. Index never calls DNR, NPS, or Met Council.
  class ParksController < BaseController
    before_action :authenticate_user_json!, only: :user_state

    def index
      parks = Park.in_state.order(:name)
      render json: {
        parks: parks.map { |park| serialize_park(park) },
        meta: {
          count: parks.size,
          types: Park::TYPES,
          amenities: distinct_values(:amenities),
          activities: distinct_values(:activities),
          attribution: attribution
        }
      }
    end

    def show
      park = Park.in_state.find(params[:id])
      render json: { park: serialize_park(park) }
    end

    def random
      park = Park.in_state.order(Arel.sql("RANDOM()")).first
      if park
        render json: { park: serialize_park(park) }
      else
        render json: { error: "No parks are loaded yet." }, status: :not_found
      end
    end

    def user_state
      park = Park.in_state.find(params[:id])
      state = current_user.park_user_states.find_or_initialize_by(park: park)
      state.favorited = ActiveModel::Type::Boolean.new.cast(params[:favorited]) if params.key?(:favorited)
      state.visited = ActiveModel::Type::Boolean.new.cast(params[:visited]) if params.key?(:visited)
      state.save!
      render json: { park: park.as_api_json(user: current_user, state: state) }
    end

    private

    def distinct_values(column)
      Park.in_state.where("jsonb_array_length(#{column}) > 0").pluck(column).flatten.uniq.sort
    end

    def attribution
      Park.shipped_payload["attribution"] || []
    rescue Errno::ENOENT, JSON::ParserError
      []
    end
  end
end
