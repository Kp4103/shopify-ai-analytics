# frozen_string_literal: true

class CreateRequestLogs < ActiveRecord::Migration[7.1]
  def change
    create_table :request_logs do |t|
      t.references :store, null: false, foreign_key: true
      t.text :question, null: false
      t.text :response
      t.text :query_used
      t.string :conversation_id
      t.boolean :success, default: false
      t.text :error
      t.json :metadata
      t.datetime :started_at
      t.datetime :completed_at
      t.integer :duration_ms

      t.timestamps
    end

    add_index :request_logs, :conversation_id
    add_index :request_logs, :created_at
    add_index :request_logs, :success
  end
end
