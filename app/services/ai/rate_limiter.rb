# frozen_string_literal: true

module Ai
  class RateLimiter
    LIMIT = 20
    WINDOW = 10.minutes

    class << self
      def reset!
        mutex.synchronize { hits.clear }
      end

      def allow?(ip:, user_id: nil)
        now = Process.clock_gettime(Process::CLOCK_MONOTONIC)
        mutex.synchronize do
          return false unless under_limit?("ip:#{ip}", now)
          return false if user_id && !under_limit?("user:#{user_id}", now)

          record("ip:#{ip}", now)
          record("user:#{user_id}", now) if user_id
          true
        end
      end

      private

      def mutex
        @mutex ||= Mutex.new
      end

      def hits
        @hits ||= Hash.new { |hash, key| hash[key] = [] }
      end

      def under_limit?(key, now)
        prune(key, now)
        hits[key].length < LIMIT
      end

      def record(key, now)
        hits[key] << now
      end

      def prune(key, now)
        cutoff = now - WINDOW.to_f
        hits[key].reject! { |stamp| stamp < cutoff }
      end
    end
  end
end
