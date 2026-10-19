class AddSourceUrlHubToParks < ActiveRecord::Migration[8.1]
  def change
    add_column :parks, :source_url_hub, :boolean, null: false, default: false
  end
end
