module Api
  class TripParksController < BaseController
    before_action { authenticate_user_json!("Sign in to create trip lists.") }
    before_action :set_own_trip

    def create
      return if performed?

      park = Park.in_state.find_by(id: params[:park_id])
      unless park
        return render json: { error: "That park was not found." }, status: :not_found
      end

      if @trip.trip_parks.exists?(park_id: park.id)
        return render json: { trip: serialize_trip }, status: :ok
      end

      @trip.trip_parks.create!(park: park, position: @trip.trip_parks.maximum(:position).to_i + 1)
      reload_trip
      render json: { trip: serialize_trip }, status: :created
    end

    def destroy
      return if performed?

      item = @trip.trip_parks.find_by(park_id: params[:id])
      unless item
        return render json: { error: "That park is not on this list." }, status: :not_found
      end

      item.destroy!
      reload_trip
      render json: { trip: serialize_trip }
    end

    private

    def set_own_trip
      return if performed? || !current_user

      @trip = current_user.trips.includes(trip_parks: :park).find_by(id: params[:trip_id])
      not_found_trip unless @trip
    end

    def reload_trip
      @trip = current_user.trips.includes(trip_parks: :park).find(@trip.id)
    end

    def serialize_trip
      parks = @trip.trip_parks.filter_map do |item|
        next unless item.park

        serialize_park(item.park).merge(position: item.position)
      end
      @trip.as_api_json(viewer: current_user, parks: parks)
    end
  end
end
