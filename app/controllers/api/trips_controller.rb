module Api
  class TripsController < BaseController
    before_action only: [ :index, :create, :update, :destroy ] do
      authenticate_user_json!("Sign in to create trip lists.")
    end
    before_action :set_own_trip, only: [ :update, :destroy ]

    def index
      trips = current_user.trips.includes(:trip_parks).newest_first
      render json: { trips: trips.map { |trip| trip.as_api_json(viewer: current_user) } }
    end

    def public_index
      trips = Trip.listed_public.includes(:trip_parks).newest_first.limit(100)
      render json: { trips: trips.map { |trip| trip.as_api_json(viewer: current_user) } }
    end

    def show
      trip = Trip.includes(trip_parks: :park).find_by(id: params[:id])
      return not_found_trip unless trip && visible?(trip)

      render json: { trip: serialize_trip(trip) }
    end

    def create
      trip = current_user.trips.new(trip_params)
      if trip.save
        render json: { trip: serialize_trip(trip) }, status: :created
      else
        render json: { error: trip.errors.full_messages.to_sentence }, status: :unprocessable_content
      end
    end

    def update
      if @trip.update(trip_params)
        render json: { trip: serialize_trip(@trip) }
      else
        render json: { error: @trip.errors.full_messages.to_sentence }, status: :unprocessable_content
      end
    end

    def destroy
      @trip.destroy!
      head :no_content
    end

    private

    def set_own_trip
      return if performed? || !current_user

      @trip = current_user.trips.includes(trip_parks: :park).find_by(id: params[:id])
      not_found_trip unless @trip
    end

    def visible?(trip)
      trip.listed_public? || trip.user_id == current_user&.id
    end

    def serialize_trip(trip)
      parks = trip.trip_parks.filter_map do |item|
        next unless item.park

        serialize_park(item.park).merge(position: item.position)
      end
      trip.as_api_json(viewer: current_user, parks: parks)
    end

    def trip_params
      permitted = {}
      permitted[:name] = params[:name] if params.key?(:name)
      permitted[:notes] = params[:notes] if params.key?(:notes)
      permitted[:status] = params[:status] if params.key?(:status)
      if params.key?(:public)
        permitted[:listed_public] = ActiveModel::Type::Boolean.new.cast(params[:public])
      end
      permitted[:starts_on] = params[:starts_on].presence if params.key?(:starts_on)
      permitted[:ends_on] = params[:ends_on].presence if params.key?(:ends_on)
      permitted
    end
  end
end
