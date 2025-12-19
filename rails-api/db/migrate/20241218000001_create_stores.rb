# frozen_string_literal: true

class CreateStores < ActiveRecord::Migration[7.1]
  def change
    create_table :stores do |t|
      t.string :shop_domain, null: false
      t.string :encrypted_access_token
      t.string :encrypted_access_token_iv
      t.string :scopes
      t.boolean :active, default: true

      t.timestamps
    end

    add_index :stores, :shop_domain, unique: true
    add_index :stores, :active
  end
end
