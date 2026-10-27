# frozen_string_literal: true

module Ai
  class Gazetteer
    PATH = Rails.root.join("db/data/mn_gazetteer.json")

    Place = Struct.new(:name, :aliases, :kind, :latitude, :longitude, :radius_miles, keyword_init: true)

    class << self
      def reset!
        @places = nil
      end

      def places
        @places ||= JSON.parse(PATH.read).fetch("places").map do |row|
          Place.new(
            name: row.fetch("name"),
            aliases: Array(row["aliases"]).map { |alias_name| normalize(alias_name) },
            kind: row["kind"],
            latitude: row.fetch("latitude").to_f,
            longitude: row.fetch("longitude").to_f,
            radius_miles: row.fetch("radius_miles").to_f
          )
        end
      end

      def match(text)
        normalized = normalize(text)
        best = nil
        best_length = 0
        places.each do |place|
          place.aliases.each do |alias_name|
            next if alias_name.length < best_length
            next unless phrase?(normalized, alias_name)

            best = place
            best_length = alias_name.length
          end
        end
        best
      end

      def phrase?(haystack, needle)
        return false if needle.blank?

        haystack.match?(/\b#{Regexp.escape(needle)}\b/)
      end

      def normalize(text)
        text.to_s.downcase.tr("’", "'").gsub(/[^\w'.]+/, " ").squeeze(" ").strip
      end
    end
  end
end
