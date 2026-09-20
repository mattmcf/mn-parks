# frozen_string_literal: true

Rails.application.config.session_store :cookie_store,
                                       key: "_mn_parks_session",
                                       same_site: :lax,
                                       expire_after: 30.days
