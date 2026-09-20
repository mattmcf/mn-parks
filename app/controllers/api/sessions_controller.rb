module Api
  class SessionsController < BaseController
    def csrf
      render json: payload(user: current_user)
    end

    def show
      render json: payload(user: current_user)
    end

    def create
      email = params[:email].to_s.downcase.strip
      user = User.find_for_database_authentication(email: email)

      unless user&.valid_password?(params[:password].to_s)
        return render json: { error: "That email or password did not match." }, status: :unauthorized
      end

      sign_in(:user, user)
      render json: payload(user: user)
    end

    def destroy
      sign_out(:user)
      render json: payload(user: nil)
    end

    private

    def payload(user:)
      {
        user: user&.as_api_json,
        csrf_token: form_authenticity_token,
        google_oauth: google_oauth_enabled?
      }
    end
  end
end
