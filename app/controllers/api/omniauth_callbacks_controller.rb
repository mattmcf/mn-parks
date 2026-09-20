module Api
  class OmniauthCallbacksController < BaseController
    skip_before_action :verify_authenticity_token
    skip_before_action :set_csrf_cookie

    def google_oauth2
      auth = request.env["omniauth.auth"]
      unless auth
        return redirect_to frontend("/?auth=error"), allow_other_host: true
      end

      user = User.from_omniauth(auth)
      sign_in(:user, user)
      redirect_to frontend("/?auth=ok"), allow_other_host: true
    end

    def failure
      redirect_to frontend("/?auth=error"), allow_other_host: true
    end

    private

    def frontend(path)
      "#{ENV.fetch("FRONTEND_ORIGIN", "http://127.0.0.1:4174")}#{path}"
    end
  end
end
