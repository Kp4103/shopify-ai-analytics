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

ActiveRecord::Schema[8.1].define(version: 2024_12_18_000002) do
  # These are extensions that must be enabled in order to support this database
  enable_extension "pg_catalog.plpgsql"

  create_table "request_logs", force: :cascade do |t|
    t.datetime "completed_at"
    t.string "conversation_id"
    t.datetime "created_at", null: false
    t.integer "duration_ms"
    t.text "error"
    t.json "metadata"
    t.text "query_used"
    t.text "question", null: false
    t.text "response"
    t.datetime "started_at"
    t.bigint "store_id", null: false
    t.boolean "success", default: false
    t.datetime "updated_at", null: false
    t.index ["conversation_id"], name: "index_request_logs_on_conversation_id"
    t.index ["created_at"], name: "index_request_logs_on_created_at"
    t.index ["store_id"], name: "index_request_logs_on_store_id"
    t.index ["success"], name: "index_request_logs_on_success"
  end

  create_table "stores", force: :cascade do |t|
    t.boolean "active", default: true
    t.datetime "created_at", null: false
    t.string "encrypted_access_token"
    t.string "encrypted_access_token_iv"
    t.string "scopes"
    t.string "shop_domain", null: false
    t.datetime "updated_at", null: false
    t.index ["active"], name: "index_stores_on_active"
    t.index ["shop_domain"], name: "index_stores_on_shop_domain", unique: true
  end

  add_foreign_key "request_logs", "stores"
end
