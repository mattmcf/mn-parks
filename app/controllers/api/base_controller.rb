module Api
  class BaseController < ApplicationController
    skip_before_action :verify_authenticity_token, if: :json_request?
    before_action :set_csrf_cookie
    respond_to :json

    private

    def json_request?
      request.format.json? || request.content_type&.include?("application/json")
    end

    def set_csrf_cookie
      cookies["X-CSRF-Token"] = {
        value: form_authenticity_token,
        same_site: :lax,
        httponly: false
      }
    end

    def current_states_by_park
      return {} unless current_user

      @current_states_by_park ||= current_user.park_user_states.index_by(&:park_id)
    end

    def serialize_park(park)
      park.as_api_json(user: current_user, state: current_states_by_park[park.id])
    end

    def authenticate_user_json!
      return if user_signed_in?

      render json: { error: "Sign in to save favorites and visited parks." }, status: :unauthorized
    end

    def google_oauth_enabled?
      ENV["GOOGLE_CLIENT_ID"].present? && ENV["GOOGLE_CLIENT_SECRET"].present?
    end
  end
end
