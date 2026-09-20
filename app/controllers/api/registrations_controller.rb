module Api
  class RegistrationsController < BaseController
    def create
      user = User.new(email: params[:email].to_s.downcase.strip, password: params[:password], password_confirmation: params[:password_confirmation] || params[:password])

      if user.save
        sign_in(:user, user)
        render json: {
          user: user.as_api_json,
          csrf_token: form_authenticity_token,
          google_oauth: google_oauth_enabled?
        }, status: :created
      else
        render json: { error: user.errors.full_messages.to_sentence }, status: :unprocessable_content
      end
    end
  end
end
