class CreateTrips < ActiveRecord::Migration[8.1]
  def change
    create_table :trips do |t|
      t.references :user, null: false, foreign_key: true
      t.string :name, null: false
      t.text :notes
      t.string :status, null: false, default: "planned"
      t.boolean :listed_public, null: false, default: false
      t.date :starts_on
      t.date :ends_on
      t.timestamps
    end

    add_index :trips, :listed_public
    add_index :trips, [ :user_id, :updated_at ]

    create_table :trip_parks do |t|
      t.references :trip, null: false, foreign_key: true
      t.references :park, null: false, foreign_key: true
      t.integer :position, null: false, default: 0
      t.timestamps
    end

    add_index :trip_parks, [ :trip_id, :park_id ], unique: true
    add_index :trip_parks, [ :trip_id, :position ]
  end
end
