# frozen_string_literal: true

module Ai
  class Planner
    NO_MATCH = "Nothing in our inventory matches that. Many county and regional parks have no amenities listed yet, so a miss is often missing data, not a missing park."
    EMPTY_PROMPT = "Tell me what you want to do — camping with showers, dark skies, a North Shore weekend…"
    NEAR_ME_HINT = "I can rank parks near you once you share a location — use GPS or drop a From pin on the map."
    MAX_RESULTS = 8
    MAX_TRIP_PARKS = 6
    NEAR_ME_MILES = 40
    EARTH_MILES = 3958.8

    TYPE_PHRASES = {
      "state" => [ "state park", "state parks" ],
      "county" => [ "county park", "county parks" ],
      "national" => [ "national park", "national parks" ],
      "regional" => [ "regional park", "regional parks" ],
      "wilderness" => [ "wilderness" ]
    }.freeze

    AMENITY_SYNONYMS = {
      "hiking" => [ "hiking", "hike", "hikes", "trails", "trail" ],
      "camping" => [ "camping", "camp", "campsite", "campsites", "tent" ],
      "swimming" => [ "swimming", "swim" ],
      "fishing" => [ "fishing", "fish" ],
      "boating" => [ "boating", "boat" ],
      "picnic" => [ "picnic", "picnics", "picnicking" ],
      "visitor_center" => [ "visitor center", "visitor centre" ],
      "playground" => [ "playground", "playgrounds" ],
      "biking" => [ "biking", "bike", "cycling" ],
      "wildlife" => [ "wildlife" ],
      "climbing" => [ "climbing", "climb" ],
      "horseback" => [ "horseback", "horseback riding" ],
      "beach" => [ "beach", "beaches" ],
      "canoeing" => [ "canoeing", "canoe", "kayak", "kayaking", "paddling" ],
      "cross_country_skiing" => [ "cross-country skiing", "cross country skiing", "xc skiing" ],
      "snowshoeing" => [ "snowshoeing", "snowshoe" ],
      "winter_sports" => [ "winter sports" ],
      "waterfall" => [ "waterfall", "waterfalls" ],
      "historic" => [ "historic", "lighthouse" ]
    }.freeze

    NAME_STOP = %w[
      state park parks county national regional wilderness area lake river falls
      minnesota mn the and with for from near around
    ].freeze

    QUERY_STOP = %w[
      a an the and or with for to of in on at by my me i we want looking looking
      some any please suggest make plan trip trips weekend itinerary parks park
      minnesota mn place places go going visit visiting find show list looking
      that this those these there here around about would like like need can you
      dark sky skies
    ].freeze

    Result = Struct.new(:message, :park_ids, :proposed_trip, :filters, keyword_init: true)
    Query = Struct.new(
      :raw, :types, :amenities, :dark_sky, :camping, :showers, :place, :near_me,
      :unknown_place, :name_tokens, :trip_intent, :blank, :garbage,
      keyword_init: true
    )

    def self.provider
      value = ENV["AI_LLM_PROVIDER"].to_s.strip
      value.presence || "mock"
    end

    def self.plan(messages:, origin: nil, parks:)
      # First slice: mock/local/unset (and any unknown provider) stay in-process.
      # A later slice may parse the prompt into this same Query schema, then rank.
      new(messages: messages, origin: origin, parks: parks).plan
    end

    def initialize(messages:, origin: nil, parks:)
      @messages = Array(messages)
      @origin = normalize_origin(origin)
      @parks = Array(parks).map { |park| project(park) }
    end

    def plan
      text = last_user_text
      query = interpret(text)

      if query.blank
        return Result.new(message: EMPTY_PROMPT, park_ids: [], proposed_trip: nil, filters: filter_json(query))
      end

      if query.garbage || no_signals?(query)
        return Result.new(message: NO_MATCH, park_ids: [], proposed_trip: nil, filters: filter_json(query))
      end

      if query.near_me && @origin.nil? && query.place.nil? && query.types.empty? && query.amenities.empty? && !query.dark_sky && query.name_tokens.empty?
        return Result.new(message: NEAR_ME_HINT, park_ids: [], proposed_trip: nil, filters: filter_json(query))
      end

      if query.unknown_place && !query.place && query.types.empty? && query.amenities.empty? && !query.dark_sky && query.name_tokens.empty?
        return Result.new(
          message: unknown_place_message(query.unknown_place),
          park_ids: [],
          proposed_trip: nil,
          filters: filter_json(query)
        )
      end

      ranked = rank(query)
      message = compose_message(query, ranked)
      ids = ranked.map { |row| row[:id] }
      trip = propose_trip(query, ranked)

      Result.new(message: message, park_ids: ids, proposed_trip: trip, filters: filter_json(query))
    end

    private

    def last_user_text
      user = @messages.reverse.find { |message| message_role(message) == "user" }
      message_content(user).to_s.strip
    end

    def message_role(message)
      (message.is_a?(Hash) ? (message[:role] || message["role"]) : nil).to_s
    end

    def message_content(message)
      message.is_a?(Hash) ? (message[:content] || message["content"]) : nil
    end

    def interpret(text)
      query = Query.new(
        raw: text,
        types: [],
        amenities: [],
        dark_sky: false,
        camping: false,
        showers: false,
        place: nil,
        near_me: false,
        unknown_place: nil,
        name_tokens: [],
        trip_intent: false,
        blank: text.blank?,
        garbage: false
      )
      return query if query.blank

      normalized = Gazetteer.normalize(text)
      query.trip_intent = trip_intent?(normalized)
      query.near_me = normalized.match?(/\b(near me|around me|close to me|nearby)\b/)
      query.dark_sky = normalized.match?(/\bdark\s*sky|\bdarksky|\bstargaz|\bnight sky\b/)
      query.showers = normalized.match?(/\bshowers?\b/)
      query.place = Gazetteer.match(normalized)

      TYPE_PHRASES.each do |type, phrases|
        query.types << type if phrases.any? { |phrase| Gazetteer.phrase?(normalized, phrase) }
      end
      query.types.uniq!

      AMENITY_SYNONYMS.each do |amenity, synonyms|
        next unless synonyms.any? { |synonym| Gazetteer.phrase?(normalized, synonym) }

        query.amenities << amenity
      end
      if query.showers
        query.amenities << "camping" unless query.amenities.include?("camping")
        query.camping = true
      end
      query.camping ||= query.amenities.include?("camping")
      query.amenities.uniq!

      query.name_tokens = name_tokens_for(normalized)
      query.unknown_place = unknown_place_from(normalized, query)
      query.garbage = garbage?(normalized, query)
      query
    end

    def trip_intent?(normalized)
      normalized.match?(/\b(weekend|trip|itinerary|suggest|plan a|make me|road trip)\b/)
    end

    def name_tokens_for(normalized)
      tokens = []
      @parks.each do |park|
        distinctive_tokens(park[:name]).each do |token|
          next unless Gazetteer.phrase?(normalized, token)

          tokens << token
        end
      end
      tokens.uniq
    end

    def distinctive_tokens(name)
      Gazetteer.normalize(name).split.reject { |token| NAME_STOP.include?(token) || token.length < 4 }
    end

    def unknown_place_from(normalized, query)
      match = normalized.match(/\bnear\s+(?!me\b)(.+)$/)
      return nil unless match

      candidate = match[1].to_s.split.first(4).join(" ").gsub(/\b(minnesota|mn)\b/, "").strip
      return nil if candidate.blank?
      return nil if query.place && Gazetteer.phrase?(candidate, query.place.aliases.max_by(&:length).to_s)
      return nil if query.name_tokens.any? { |token| Gazetteer.phrase?(candidate, token) }
      return nil if QUERY_STOP.include?(candidate)

      candidate
    end

    def garbage?(normalized, query)
      return false unless no_signals?(query)

      leftover = normalized.split.reject { |token| QUERY_STOP.include?(token) || token.length < 3 }
      leftover.any?
    end

    def no_signals?(query)
      query.types.empty? && query.amenities.empty? && !query.dark_sky && query.place.nil? &&
        !query.near_me && query.name_tokens.empty? && query.unknown_place.nil?
    end

    def rank(query)
      origin = ranking_origin(query)
      scored = @parks.filter_map do |park|
        next unless type_ok?(park, query)
        next unless dark_sky_ok?(park, query)
        next unless name_ok?(park, query)
        next unless place_ok?(park, query, origin)
        next unless amenities_ok?(park, query)

        [ score(park, query, origin), park ]
      end

      if scored.empty? && query.amenities.any? && (query.place || query.types.any? || query.dark_sky || query.name_tokens.any?)
        relaxed = query.dup
        # Keep amenity preference in scoring, but do not require every amenity.
        scored = @parks.filter_map do |park|
          next unless type_ok?(park, relaxed)
          next unless dark_sky_ok?(park, relaxed)
          next unless name_ok?(park, relaxed)
          next unless place_ok?(park, relaxed, origin)
          next if amenity_hits(park, query).zero?

          [ score(park, query, origin), park ]
        end
      end

      scored.sort_by { |points, park| [ -points, park[:name] ] }.first(MAX_RESULTS).map(&:last)
    end

    def type_ok?(park, query)
      query.types.empty? || query.types.include?(park[:park_type])
    end

    def dark_sky_ok?(park, query)
      !query.dark_sky || park[:dark_sky_certified] == true
    end

    def name_ok?(park, query)
      return true if query.name_tokens.empty?

      tokens = distinctive_tokens(park[:name])
      query.name_tokens.any? { |token| tokens.include?(token) }
    end

    def place_ok?(park, query, origin)
      return true unless origin && (query.place || query.near_me)

      radius = query.place&.radius_miles || NEAR_ME_MILES
      miles_between(origin, park) <= radius
    end

    def amenities_ok?(park, query)
      return true if query.amenities.empty?

      query.amenities.all? { |amenity| has_amenity?(park, amenity) }
    end

    def has_amenity?(park, amenity)
      return camping_listed?(park) if amenity == "camping"

      listed?(park[:amenities], amenity) || listed?(park[:activities], amenity) ||
        listed?(park[:activities], amenity.tr("_", " ")) ||
        listed?(park[:activities], amenity.tr("_", "-"))
    end

    def camping_listed?(park)
      listed?(park[:amenities], "camping") || listed?(park[:activities], "camping") ||
        park[:camping_score].present? || park.dig(:camping, :kind).present? || park.dig(:camping, "kind").present?
    end

    def listed?(values, needle)
      Array(values).map { |value| value.to_s.downcase }.include?(needle.to_s.downcase)
    end

    def amenity_hits(park, query)
      query.amenities.count { |amenity| has_amenity?(park, amenity) }
    end

    def ranking_origin(query)
      if query.place
        { latitude: query.place.latitude, longitude: query.place.longitude }
      elsif query.near_me && @origin
        @origin
      end
    end

    def score(park, query, origin)
      points = 0.0
      points += 80 if query.name_tokens.any? { |token| distinctive_tokens(park[:name]).include?(token) }
      points += 60 if query.dark_sky && park[:dark_sky_certified]
      points += amenity_hits(park, query) * 18
      if query.camping && park[:camping_score]
        points += park[:camping_score].to_f * 12
      end
      if query.showers
        snippet = camping_snippet(park).to_s.downcase
        points += 10 if snippet.include?("shower") || snippet.include?("electric")
      end
      if origin
        miles = miles_between(origin, park)
        points += [ 40 - miles, 0 ].max * 0.4
      end
      points
    end

    def compose_message(query, parks)
      return unknown_place_with_results(query, parks) if parks.any? && query.unknown_place
      return NO_MATCH if parks.empty?
      return NEAR_ME_HINT if query.near_me && @origin.nil? && parks.empty?

      criteria = criteria_bits(query)
      lead = if parks.length == 1
        "I found 1 park in our inventory that matches #{criteria}."
      else
        "I found #{parks.length} parks in our inventory that match #{criteria}."
      end

      lines = parks.map { |park| "• #{park_line(park, query)}" }
      extras = []
      extras << shower_caveat if query.showers
      extras << "Certified DarkSky International places only — nearby dark sites are not guessed." if query.dark_sky
      extras << "Amenities I could not require from our inventory still may exist; empty lists mean not listed, not proof they are missing." if query.amenities.any? && parks.any? { |park| amenity_hits(park, query) < query.amenities.length }
      extras << NEAR_ME_HINT if query.near_me && @origin.nil?
      extras << unknown_place_message(query.unknown_place) if query.unknown_place

      ([ lead, "", *lines ] + extras.map { |extra| "\n#{extra}" }).join("\n").strip
    end

    def unknown_place_with_results(query, parks)
      "#{compose_message(query.dup.tap { |copy| copy.unknown_place = nil }, parks)}\n\n#{unknown_place_message(query.unknown_place)}"
    end

    def unknown_place_message(place)
      "I don't have a place called #{place} in our Minnesota gazetteer. Drop a From pin or name a park (or a city like Duluth) and try again."
    end

    def shower_caveat
      "Showers are not a separate amenity chip in our inventory. Parks below list camping or an official DNR/NPS camping inventory instead — I am not guessing bathroom buildings."
    end

    def criteria_bits(query)
      bits = []
      bits << query.types.map { |type| "#{type} parks" }.join(" and ") if query.types.any?
      bits << "dark sky" if query.dark_sky
      bits << query.amenities.join(" and ") if query.amenities.any?
      bits << "near #{query.place.name}" if query.place
      bits << "near you" if query.near_me && @origin
      bits << query.name_tokens.map(&:capitalize).join(" and ") if query.name_tokens.any? && bits.empty?
      bits << "camping with showers" if query.showers && bits.none? { |bit| bit.include?("camping") }
      return "what you asked" if bits.empty?

      bits.join(", ")
    end

    def park_line(park, query)
      parts = [ "#{park[:name]} (#{park[:park_type]})" ]
      details = []
      if park[:dark_sky_certified]
        label = park.dig(:dark_sky, :category_label) || park.dig(:dark_sky, "category_label")
        details << (label.present? ? "Dark Sky #{label}" : "Dark Sky certified")
      end
      if park[:camping_score]
        details << "camping score #{park[:camping_score]}"
      end
      count = park.dig(:camping, :campsite_count) || park.dig(:camping, "campsite_count")
      snippet = camping_snippet(park)
      if count
        details << "#{count} official camping units"
      elsif snippet.present? && query.camping
        details << snippet.to_s.truncate(90)
      end
      listed = Array(park[:amenities]).first(6)
      details << "#{listed.join(", ")} listed" if listed.any?
      details << "no amenities listed yet" if listed.empty?
      highlights = park[:highlights].to_s.strip
      details << highlights.truncate(90) if highlights.present?
      parts << " — #{details.join(". ")}" if details.any?
      parts.join
    end

    def camping_snippet(park)
      park.dig(:camping, :snippet) || park.dig(:camping, "snippet")
    end

    def propose_trip(query, parks)
      return nil if parks.empty?

      chosen = parks.first(MAX_TRIP_PARKS)
      name = trip_name(query, chosen)
      notes = trip_notes(query, chosen)
      {
        "name" => name,
        "notes" => notes,
        "status" => "planned",
        "park_ids" => chosen.map { |park| park[:id] }
      }
    end

    def trip_name(query, parks)
      return "#{query.place.name} weekend" if query.place && query.trip_intent
      return "#{query.place.name} parks" if query.place
      return "Dark Sky parks" if query.dark_sky
      if query.types.any? && query.amenities.any?
        return "#{query.types.first.capitalize} parks with #{query.amenities.join(" and ")}"
      end
      return "#{query.name_tokens.first.capitalize} camping" if query.name_tokens.any? && query.camping
      return parks.first[:name] if parks.length == 1

      "Minnesota parks"
    end

    def trip_notes(query, parks)
      bits = [ "Suggested from the MN Parks inventory (not live GIS or reviews)." ]
      bits << "Criteria: #{criteria_bits(query)}."
      bits << parks.map { |park| park[:name] }.join(", ") + "."
      bits.join(" ").truncate(4000)
    end

    def filter_json(query)
      {
        types: query.types,
        amenities: query.amenities,
        dark_sky: query.dark_sky,
        camping: query.camping,
        showers: query.showers,
        place: query.place&.name,
        near_me: query.near_me,
        unknown_place: query.unknown_place,
        name_tokens: query.name_tokens,
        garbage: query.garbage
      }
    end

    def project(park)
      if park.respond_to?(:as_api_json) && !park.is_a?(Hash)
        json = park.as_api_json
        {
          id: json[:id] || park.id,
          name: json[:name],
          park_type: json[:park_type],
          latitude: json[:latitude].to_f,
          longitude: json[:longitude].to_f,
          highlights: json[:highlights],
          amenities: json[:amenities] || [],
          activities: json[:activities] || [],
          dark_sky_certified: json[:dark_sky_certified],
          dark_sky: json[:dark_sky],
          camping_score: json[:camping_score],
          camping: json[:camping]
        }
      else
        row = park.stringify_keys
        camping = row["camping"]
        camping = camping.stringify_keys if camping.is_a?(Hash)
        dark = row["dark_sky"]
        dark = dark.stringify_keys if dark.is_a?(Hash)
        {
          id: row.fetch("id"),
          name: row.fetch("name"),
          park_type: row.fetch("park_type"),
          latitude: row["latitude"].to_f,
          longitude: row["longitude"].to_f,
          highlights: row["highlights"],
          amenities: row["amenities"] || [],
          activities: row["activities"] || [],
          dark_sky_certified: ActiveModel::Type::Boolean.new.cast(row["dark_sky_certified"]),
          dark_sky: dark,
          camping_score: row["camping_score"]&.to_f,
          camping: camping
        }
      end
    end

    def normalize_origin(origin)
      return nil if origin.blank?

      row = origin.respond_to?(:to_unsafe_h) ? origin.to_unsafe_h : origin
      row = row.stringify_keys
      lat = row["latitude"]
      lng = row["longitude"]
      return nil if lat.blank? || lng.blank?

      { latitude: lat.to_f, longitude: lng.to_f }
    end

    def miles_between(origin, park)
      lat1 = origin[:latitude] * Math::PI / 180
      lat2 = park[:latitude] * Math::PI / 180
      dlat = lat2 - lat1
      dlng = (park[:longitude] - origin[:longitude]) * Math::PI / 180
      split = Math.sin(dlat / 2)**2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlng / 2)**2
      2 * EARTH_MILES * Math.asin([ 1, Math.sqrt(split) ].min)
    end
  end
end
