# This file is auto-generated from the current state of the database. Instead
# of editing this file, please use the migrations feature of Active Record to
# incrementally modify your database, and then regenerate this schema definition.
#
# This file is the source Rails uses to define your schema when running `bin/rails
# db:schema:load`. When creating a new database, `bin/rails db:schema:load` tends to
# be faster and is potentially less error prone than running all of your
# migrations from scratch. Old migrations may fail to apply correctly if those
# migrations use external dependencies or application code.
#
# It's strongly recommended that you check this file into your version control system.

ActiveRecord::Schema[8.1].define(version: 2026_09_20_180616) do
  # These are extensions that must be enabled in order to support this database
  enable_extension "pg_catalog.plpgsql"

  create_table "park_user_states", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.boolean "favorited", default: false, null: false
    t.bigint "park_id", null: false
    t.datetime "updated_at", null: false
    t.bigint "user_id", null: false
    t.boolean "visited", default: false, null: false
    t.index ["park_id"], name: "index_park_user_states_on_park_id"
    t.index ["user_id", "park_id"], name: "index_park_user_states_on_user_id_and_park_id", unique: true
    t.index ["user_id"], name: "index_park_user_states_on_user_id"
  end

  create_table "parks", force: :cascade do |t|
    t.jsonb "activities", default: -> { "'[]'::jsonb" }, null: false
    t.jsonb "amenities", default: -> { "'[]'::jsonb" }, null: false
    t.datetime "created_at", null: false
    t.text "highlights"
    t.boolean "in_minnesota", default: true, null: false
    t.decimal "latitude", precision: 10, scale: 7, null: false
    t.decimal "longitude", precision: 10, scale: 7, null: false
    t.string "managing_agency"
    t.string "name", null: false
    t.string "park_type", null: false
    t.datetime "retrieved_at"
    t.string "source", null: false
    t.string "source_id", null: false
    t.string "source_url"
    t.datetime "updated_at", null: false
    t.index ["activities"], name: "index_parks_on_activities", using: :gin
    t.index ["amenities"], name: "index_parks_on_amenities", using: :gin
    t.index ["name"], name: "index_parks_on_name"
    t.index ["park_type"], name: "index_parks_on_park_type"
    t.index ["source", "source_id"], name: "index_parks_on_source_and_source_id", unique: true
  end

  create_table "users", force: :cascade do |t|
    t.datetime "created_at", null: false
    t.string "email", default: "", null: false
    t.string "encrypted_password", default: "", null: false
    t.string "provider"
    t.datetime "remember_created_at"
    t.datetime "reset_password_sent_at"
    t.string "reset_password_token"
    t.string "uid"
    t.datetime "updated_at", null: false
    t.index ["email"], name: "index_users_on_email", unique: true
    t.index ["provider", "uid"], name: "index_users_on_provider_and_uid", unique: true, where: "((provider IS NOT NULL) AND (uid IS NOT NULL))"
    t.index ["reset_password_token"], name: "index_users_on_reset_password_token", unique: true
  end

  add_foreign_key "park_user_states", "parks"
  add_foreign_key "park_user_states", "users"
end
