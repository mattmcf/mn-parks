class CreateParkUserStates < ActiveRecord::Migration[8.1]
  def change
    create_table :park_user_states do |t|
      t.references :user, null: false, foreign_key: true
      t.references :park, null: false, foreign_key: true
      t.boolean :favorited, null: false, default: false
      t.boolean :visited, null: false, default: false
      t.timestamps
    end

    add_index :park_user_states, [ :user_id, :park_id ], unique: true
  end
end
