class AddParkIntelToParks < ActiveRecord::Migration[8.1]
  def change
    add_column :parks, :dark_sky_certified, :boolean, null: false, default: false
    add_column :parks, :dark_sky, :jsonb, null: false, default: -> { "'{}'::jsonb" }
    add_column :parks, :camping_score, :decimal, precision: 3, scale: 1
    add_column :parks, :camping, :jsonb, null: false, default: -> { "'{}'::jsonb" }

    add_index :parks, :dark_sky_certified
    add_index :parks, :camping_score
  end
end
