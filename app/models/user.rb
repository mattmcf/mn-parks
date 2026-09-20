class User < ApplicationRecord
  devise :database_authenticatable, :registerable, :recoverable, :rememberable, :validatable

  has_many :park_user_states, dependent: :destroy
  has_many :favorited_parks, -> { where(park_user_states: { favorited: true }) },
           through: :park_user_states, source: :park
  has_many :visited_parks, -> { where(park_user_states: { visited: true }) },
           through: :park_user_states, source: :park

  def self.from_omniauth(auth)
    email = auth.info.email.to_s.downcase
    user = find_by(provider: auth.provider, uid: auth.uid)
    return user if user

    user = find_by(email: email)
    if user
      user.update!(provider: auth.provider, uid: auth.uid)
      return user
    end

    create!(
      email: email,
      password: Devise.friendly_token[0, 20],
      provider: auth.provider,
      uid: auth.uid
    )
  end

  def as_api_json
    { id: id, email: email }
  end
end
