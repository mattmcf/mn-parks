# frozen_string_literal: true

module Api
  class AiChatsController < BaseController
    def create
      unless Ai::RateLimiter.allow?(ip: request.remote_ip, user_id: current_user&.id)
        return render json: { error: "Too many planning requests. Try again in a few minutes." }, status: :too_many_requests
      end

      messages = chat_messages
      result = Ai::Planner.plan(
        messages: messages,
        origin: origin_param,
        parks: Park.in_state
      )

      parks_by_id = Park.in_state.where(id: result.park_ids).index_by(&:id)
      parks = result.park_ids.filter_map { |id| parks_by_id[id] }.map { |park| serialize_park(park) }

      Rails.logger.info({ ai_chat: { provider: Ai::Planner.provider, park_ids: result.park_ids, filters: result.filters } }.to_json)

      payload = { message: result.message, parks: parks }
      payload[:proposed_trip] = result.proposed_trip if result.proposed_trip
      render json: payload
    end

    private

    def chat_messages
      Array(params[:messages]).filter_map do |entry|
        row = entry.respond_to?(:to_unsafe_h) ? entry.to_unsafe_h : entry
        next unless row.respond_to?(:[])

        {
          role: row[:role].presence || row["role"].presence || "user",
          content: (row[:content] || row["content"]).to_s
        }
      end
    end

    def origin_param
      raw = params[:origin]
      return nil if raw.blank?

      row = raw.respond_to?(:to_unsafe_h) ? raw.to_unsafe_h : raw
      row = row.stringify_keys if row.respond_to?(:stringify_keys)
      { latitude: row["latitude"], longitude: row["longitude"] }
    end
  end
end
