class CreateParks < ActiveRecord::Migration[8.1]
  def change
    create_table :parks do |t|
      t.string :name, null: false
      t.string :park_type, null: false
      t.string :managing_agency
      t.string :source, null: false
      t.string :source_id, null: false
      t.string :source_url
      t.decimal :latitude, precision: 10, scale: 7, null: false
      t.decimal :longitude, precision: 10, scale: 7, null: false
      t.text :highlights
      t.jsonb :amenities, null: false, default: -> { "'[]'::jsonb" }
      t.jsonb :activities, null: false, default: -> { "'[]'::jsonb" }
      t.boolean :in_minnesota, null: false, default: true
      t.datetime :retrieved_at
      t.timestamps
    end

    add_index :parks, [ :source, :source_id ], unique: true
    add_index :parks, :park_type
    add_index :parks, :name
    add_index :parks, :amenities, using: :gin
    add_index :parks, :activities, using: :gin
  end
end
