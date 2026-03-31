Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "backfill_task" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "portal_id" {
    null = false
    type = text
  }
  column "portal_receiver" {
    null = false
    type = text
  }
  column "user_login_id" {
    null = false
    type = text
  }
  column "batch_count" {
    null = false
    type = integer
  }
  column "is_done" {
    null = false
    type = boolean
  }
  column "cursor" {
    null = true
    type = text
  }
  column "oldest_message_id" {
    null = true
    type = text
  }
  column "dispatched_at" {
    null = true
    type = bigint
  }
  column "completed_at" {
    null = true
    type = bigint
  }
  column "next_dispatch_min_ts" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.portal_id, column.portal_receiver]
  }
  foreign_key "backfill_queue_portal_fkey" {
    columns     = [column.bridge_id, column.portal_id, column.portal_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "database_owner" {
  schema = schema.public
  column "key" {
    null    = false
    type    = integer
    default = 0
  }
  column "owner" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.key]
  }
}
table "disappearing_message" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "mx_room" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  column "timestamp" {
    null    = false
    type    = bigint
    default = 0
  }
  column "type" {
    null = false
    type = text
  }
  column "timer" {
    null = false
    type = bigint
  }
  column "disappear_at" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.mxid]
  }
  foreign_key "disappearing_message_portal_fkey" {
    columns     = [column.bridge_id, column.mx_room]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.mxid]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "disappearing_message_portal_idx" {
    columns = [column.bridge_id, column.mx_room]
  }
}
table "ghost" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "avatar_id" {
    null = false
    type = text
  }
  column "avatar_hash" {
    null = false
    type = text
  }
  column "avatar_mxc" {
    null = false
    type = text
  }
  column "name_set" {
    null = false
    type = boolean
  }
  column "avatar_set" {
    null = false
    type = boolean
  }
  column "contact_info_set" {
    null = false
    type = boolean
  }
  column "is_bot" {
    null = false
    type = boolean
  }
  column "identifiers" {
    null = false
    type = jsonb
  }
  column "extra_profile" {
    null = true
    type = jsonb
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.bridge_id, column.id]
  }
}
table "kv_store" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "key" {
    null = false
    type = text
  }
  column "value" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.bridge_id, column.key]
  }
}
table "message" {
  schema = schema.public
  column "rowid" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "bridge_id" {
    null = false
    type = text
  }
  column "id" {
    null = false
    type = text
  }
  column "part_id" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "room_receiver" {
    null = false
    type = text
  }
  column "sender_id" {
    null = false
    type = text
  }
  column "sender_mxid" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "edit_count" {
    null = false
    type = integer
  }
  column "double_puppeted" {
    null = true
    type = boolean
  }
  column "thread_root_id" {
    null = true
    type = text
  }
  column "reply_to_id" {
    null = true
    type = text
  }
  column "reply_to_part_id" {
    null = true
    type = text
  }
  column "send_txn_id" {
    null = true
    type = text
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.rowid]
  }
  foreign_key "message_room_fkey" {
    columns     = [column.bridge_id, column.room_id, column.room_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "message_sender_fkey" {
    columns     = [column.bridge_id, column.sender_id]
    ref_columns = [table.ghost.column.bridge_id, table.ghost.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "message_room_idx" {
    columns = [column.bridge_id, column.room_id, column.room_receiver]
  }
  unique "message_mxid_unique" {
    columns = [column.bridge_id, column.mxid]
  }
  unique "message_real_pkey" {
    columns = [column.bridge_id, column.room_receiver, column.id, column.part_id]
  }
  unique "message_txn_id_unique" {
    columns = [column.bridge_id, column.room_receiver, column.send_txn_id]
  }
}
table "mx_registrations" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.user_id]
  }
}
table "mx_room_state" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "power_levels" {
    null = true
    type = jsonb
  }
  column "encryption" {
    null = true
    type = jsonb
  }
  column "create_event" {
    null = true
    type = jsonb
  }
  column "join_rules" {
    null = true
    type = jsonb
  }
  column "members_fetched" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.room_id]
  }
}
table "mx_user_profile" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "membership" {
    null = false
    type = enum.membership
  }
  column "displayname" {
    null    = false
    type    = text
    default = ""
  }
  column "avatar_url" {
    null    = false
    type    = text
    default = ""
  }
  column "name_skeleton" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.room_id, column.user_id]
  }
  index "mx_user_profile_membership_idx" {
    columns = [column.room_id, column.membership]
  }
  index "mx_user_profile_name_skeleton_idx" {
    columns = [column.room_id, column.name_skeleton]
  }
}
table "mx_version" {
  schema = schema.public
  column "version" {
    null = true
    type = integer
  }
  column "compat" {
    null = true
    type = integer
  }
}
table "portal" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "id" {
    null = false
    type = text
  }
  column "receiver" {
    null = false
    type = text
  }
  column "mxid" {
    null = true
    type = text
  }
  column "parent_id" {
    null = true
    type = text
  }
  column "parent_receiver" {
    null    = false
    type    = text
    default = ""
  }
  column "relay_bridge_id" {
    null = true
    type = text
  }
  column "relay_login_id" {
    null = true
    type = text
  }
  column "other_user_id" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "topic" {
    null = false
    type = text
  }
  column "avatar_id" {
    null = false
    type = text
  }
  column "avatar_hash" {
    null = false
    type = text
  }
  column "avatar_mxc" {
    null = false
    type = text
  }
  column "name_set" {
    null = false
    type = boolean
  }
  column "avatar_set" {
    null = false
    type = boolean
  }
  column "topic_set" {
    null = false
    type = boolean
  }
  column "name_is_custom" {
    null    = false
    type    = boolean
    default = false
  }
  column "in_space" {
    null = false
    type = boolean
  }
  column "message_request" {
    null    = false
    type    = boolean
    default = false
  }
  column "room_type" {
    null = false
    type = text
  }
  column "disappear_type" {
    null = true
    type = text
  }
  column "disappear_timer" {
    null = true
    type = bigint
  }
  column "cap_state" {
    null = true
    type = jsonb
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.bridge_id, column.id, column.receiver]
  }
  foreign_key "portal_parent_fkey" {
    columns     = [column.bridge_id, column.parent_id, column.parent_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = NO_ACTION
  }
  foreign_key "portal_relay_fkey" {
    columns     = [column.relay_bridge_id, column.relay_login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  index "portal_bridge_mxid_idx" {
    unique  = true
    columns = [column.bridge_id, column.mxid]
  }
  index "portal_parent_idx" {
    columns = [column.bridge_id, column.parent_id, column.parent_receiver]
  }
}
table "public_media" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "public_id" {
    null = false
    type = text
  }
  column "mxc" {
    null = false
    type = text
  }
  column "keys" {
    null = true
    type = jsonb
  }
  column "mimetype" {
    null = true
    type = text
  }
  column "expiry" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.public_id]
  }
}
table "reaction" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "message_part_id" {
    null = false
    type = text
  }
  column "sender_id" {
    null = false
    type = text
  }
  column "sender_mxid" {
    null    = false
    type    = text
    default = ""
  }
  column "emoji_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "room_receiver" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "emoji" {
    null = false
    type = text
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.bridge_id, column.room_receiver, column.message_id, column.message_part_id, column.sender_id, column.emoji_id]
  }
  foreign_key "reaction_message_fkey" {
    columns     = [column.bridge_id, column.room_receiver, column.message_id, column.message_part_id]
    ref_columns = [table.message.column.bridge_id, table.message.column.room_receiver, table.message.column.id, table.message.column.part_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "reaction_room_fkey" {
    columns     = [column.bridge_id, column.room_id, column.room_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "reaction_sender_fkey" {
    columns     = [column.bridge_id, column.sender_id]
    ref_columns = [table.ghost.column.bridge_id, table.ghost.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "reaction_room_idx" {
    columns = [column.bridge_id, column.room_id, column.room_receiver]
  }
  unique "reaction_mxid_unique" {
    columns = [column.bridge_id, column.mxid]
  }
}
table "user" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  column "management_room" {
    null = true
    type = text
  }
  column "access_token" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.bridge_id, column.mxid]
  }
}
table "user_login" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_mxid" {
    null = false
    type = text
  }
  column "id" {
    null = false
    type = text
  }
  column "remote_name" {
    null = false
    type = text
  }
  column "remote_profile" {
    null = true
    type = jsonb
  }
  column "space_room" {
    null = true
    type = text
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.bridge_id, column.id]
  }
  foreign_key "user_login_user_fkey" {
    columns     = [column.bridge_id, column.user_mxid]
    ref_columns = [table.user.column.bridge_id, table.user.column.mxid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "user_portal" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_mxid" {
    null = false
    type = text
  }
  column "login_id" {
    null = false
    type = text
  }
  column "portal_id" {
    null = false
    type = text
  }
  column "portal_receiver" {
    null = false
    type = text
  }
  column "in_space" {
    null = false
    type = boolean
  }
  column "preferred" {
    null = false
    type = boolean
  }
  column "last_read" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.user_mxid, column.login_id, column.portal_id, column.portal_receiver]
  }
  foreign_key "user_portal_portal_fkey" {
    columns     = [column.bridge_id, column.portal_id, column.portal_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "user_portal_user_login_fkey" {
    columns     = [column.bridge_id, column.login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "user_portal_login_idx" {
    columns = [column.bridge_id, column.login_id]
  }
  index "user_portal_portal_idx" {
    columns = [column.bridge_id, column.portal_id, column.portal_receiver]
  }
}
table "version" {
  schema = schema.public
  column "version" {
    null = true
    type = integer
  }
  column "compat" {
    null = true
    type = integer
  }
}
table "whatsapp_avatar_cache" {
  schema = schema.public
  column "entity_jid" {
    null = false
    type = text
  }
  column "avatar_id" {
    null = false
    type = text
  }
  column "direct_path" {
    null = false
    type = text
  }
  column "expiry" {
    null = false
    type = bigint
  }
  column "gone" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.entity_jid, column.avatar_id]
  }
}
table "whatsapp_history_sync_conversation" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_login_id" {
    null = false
    type = text
  }
  column "chat_jid" {
    null = false
    type = text
  }
  column "last_message_timestamp" {
    null = true
    type = bigint
  }
  column "archived" {
    null = true
    type = boolean
  }
  column "pinned" {
    null = true
    type = boolean
  }
  column "mute_end_time" {
    null = true
    type = bigint
  }
  column "end_of_history_transfer_type" {
    null = true
    type = integer
  }
  column "ephemeral_expiration" {
    null = true
    type = integer
  }
  column "ephemeral_setting_timestamp" {
    null = true
    type = bigint
  }
  column "marked_as_unread" {
    null = true
    type = boolean
  }
  column "unread_count" {
    null = true
    type = integer
  }
  column "synced_login_ts" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.user_login_id, column.chat_jid]
  }
  foreign_key "whatsapp_history_sync_conversation_user_login_fkey" {
    columns     = [column.bridge_id, column.user_login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsapp_history_sync_message" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_login_id" {
    null = false
    type = text
  }
  column "chat_jid" {
    null = false
    type = text
  }
  column "sender_jid" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "data" {
    null = false
    type = bytea
  }
  column "inserted_time" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.bridge_id, column.user_login_id, column.chat_jid, column.sender_jid, column.message_id]
  }
  foreign_key "whatsapp_history_sync_message_conversation_fkey" {
    columns     = [column.bridge_id, column.user_login_id, column.chat_jid]
    ref_columns = [table.whatsapp_history_sync_conversation.column.bridge_id, table.whatsapp_history_sync_conversation.column.user_login_id, table.whatsapp_history_sync_conversation.column.chat_jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "whatsapp_history_sync_message_user_login_fkey" {
    columns     = [column.bridge_id, column.user_login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsapp_history_sync_notification" {
  schema = schema.public
  column "rowid" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_login_id" {
    null = false
    type = text
  }
  column "data" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.rowid]
  }
  foreign_key "whatsapp_history_sync_notification_user_login_fkey" {
    columns     = [column.bridge_id, column.user_login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "whatsapp_history_sync_notification_login_idx" {
    columns = [column.bridge_id, column.user_login_id]
  }
}
table "whatsapp_media_backfill_request" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "user_login_id" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "_part_id" {
    null    = false
    type    = text
    default = ""
  }
  column "portal_id" {
    null = false
    type = text
  }
  column "portal_receiver" {
    null = false
    type = text
  }
  column "media_key" {
    null = true
    type = bytea
  }
  column "status" {
    null = false
    type = integer
  }
  column "error" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.bridge_id, column.user_login_id, column.message_id]
  }
  foreign_key "whatsapp_media_backfill_request_message_fkey" {
    columns     = [column.bridge_id, column.portal_receiver, column.message_id, column._part_id]
    ref_columns = [table.message.column.bridge_id, table.message.column.room_receiver, table.message.column.id, table.message.column.part_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "whatsapp_media_backfill_request_portal_fkey" {
    columns     = [column.bridge_id, column.portal_id, column.portal_receiver]
    ref_columns = [table.portal.column.bridge_id, table.portal.column.id, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "whatsapp_media_backfill_request_user_login_fkey" {
    columns     = [column.bridge_id, column.user_login_id]
    ref_columns = [table.user_login.column.bridge_id, table.user_login.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "whatsapp_media_backfill_request_message_idx" {
    columns = [column.bridge_id, column.portal_receiver, column.message_id, column._part_id]
  }
  index "whatsapp_media_backfill_request_portal_idx" {
    columns = [column.bridge_id, column.portal_id, column.portal_receiver]
  }
}
table "whatsapp_poll_option_id" {
  schema = schema.public
  column "bridge_id" {
    null = false
    type = text
  }
  column "msg_mxid" {
    null = false
    type = text
  }
  column "opt_id" {
    null = false
    type = text
  }
  column "opt_hash" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.bridge_id, column.msg_mxid, column.opt_id]
  }
  foreign_key "message_mxid_fkey" {
    columns     = [column.bridge_id, column.msg_mxid]
    ref_columns = [table.message.column.bridge_id, table.message.column.mxid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsapp_poll_option_id_opt_hash_check" {
    expr = "(length(opt_hash) = 32)"
  }
  unique "whatsapp_poll_option_unique_hash" {
    columns = [column.bridge_id, column.msg_mxid, column.opt_hash]
  }
}
table "whatsapp_version" {
  schema = schema.public
  column "version" {
    null = true
    type = integer
  }
  column "compat" {
    null = true
    type = integer
  }
}
table "whatsmeow_app_state_mutation_macs" {
  schema = schema.public
  column "jid" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = bigint
  }
  column "index_mac" {
    null = false
    type = bytea
  }
  column "value_mac" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.jid, column.name, column.version, column.index_mac]
  }
  foreign_key "whatsmeow_app_state_mutation_macs_jid_name_fkey" {
    columns     = [column.jid, column.name]
    ref_columns = [table.whatsmeow_app_state_version.column.jid, table.whatsmeow_app_state_version.column.name]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsmeow_app_state_mutation_macs_index_mac_check" {
    expr = "(length(index_mac) = 32)"
  }
  check "whatsmeow_app_state_mutation_macs_value_mac_check" {
    expr = "(length(value_mac) = 32)"
  }
}
table "whatsmeow_app_state_sync_keys" {
  schema = schema.public
  column "jid" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = bytea
  }
  column "key_data" {
    null = false
    type = bytea
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "fingerprint" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.jid, column.key_id]
  }
  foreign_key "whatsmeow_app_state_sync_keys_jid_fkey" {
    columns     = [column.jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_app_state_version" {
  schema = schema.public
  column "jid" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = bigint
  }
  column "hash" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.jid, column.name]
  }
  foreign_key "whatsmeow_app_state_version_jid_fkey" {
    columns     = [column.jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsmeow_app_state_version_hash_check" {
    expr = "(length(hash) = 128)"
  }
}
table "whatsmeow_chat_settings" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "chat_jid" {
    null = false
    type = text
  }
  column "muted_until" {
    null    = false
    type    = bigint
    default = 0
  }
  column "pinned" {
    null    = false
    type    = boolean
    default = false
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.our_jid, column.chat_jid]
  }
  foreign_key "whatsmeow_chat_settings_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_contacts" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "their_jid" {
    null = false
    type = text
  }
  column "first_name" {
    null = true
    type = text
  }
  column "full_name" {
    null = true
    type = text
  }
  column "push_name" {
    null = true
    type = text
  }
  column "business_name" {
    null = true
    type = text
  }
  column "redacted_phone" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.our_jid, column.their_jid]
  }
  foreign_key "whatsmeow_contacts_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_device" {
  schema = schema.public
  column "jid" {
    null = false
    type = text
  }
  column "lid" {
    null = true
    type = text
  }
  column "facebook_uuid" {
    null = true
    type = uuid
  }
  column "registration_id" {
    null = false
    type = bigint
  }
  column "noise_key" {
    null = false
    type = bytea
  }
  column "identity_key" {
    null = false
    type = bytea
  }
  column "signed_pre_key" {
    null = false
    type = bytea
  }
  column "signed_pre_key_id" {
    null = false
    type = integer
  }
  column "signed_pre_key_sig" {
    null = false
    type = bytea
  }
  column "adv_key" {
    null = false
    type = bytea
  }
  column "adv_details" {
    null = false
    type = bytea
  }
  column "adv_account_sig" {
    null = false
    type = bytea
  }
  column "adv_account_sig_key" {
    null = false
    type = bytea
  }
  column "adv_device_sig" {
    null = false
    type = bytea
  }
  column "platform" {
    null    = false
    type    = text
    default = ""
  }
  column "business_name" {
    null    = false
    type    = text
    default = ""
  }
  column "push_name" {
    null    = false
    type    = text
    default = ""
  }
  column "lid_migration_ts" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.jid]
  }
  check "whatsmeow_device_adv_account_sig_check" {
    expr = "(length(adv_account_sig) = 64)"
  }
  check "whatsmeow_device_adv_account_sig_key_check" {
    expr = "(length(adv_account_sig_key) = 32)"
  }
  check "whatsmeow_device_adv_device_sig_check" {
    expr = "(length(adv_device_sig) = 64)"
  }
  check "whatsmeow_device_identity_key_check" {
    expr = "(length(identity_key) = 32)"
  }
  check "whatsmeow_device_noise_key_check" {
    expr = "(length(noise_key) = 32)"
  }
  check "whatsmeow_device_registration_id_check" {
    expr = "((registration_id >= 0) AND (registration_id < '4294967296'::bigint))"
  }
  check "whatsmeow_device_signed_pre_key_check" {
    expr = "(length(signed_pre_key) = 32)"
  }
  check "whatsmeow_device_signed_pre_key_id_check" {
    expr = "((signed_pre_key_id >= 0) AND (signed_pre_key_id < 16777216))"
  }
  check "whatsmeow_device_signed_pre_key_sig_check" {
    expr = "(length(signed_pre_key_sig) = 64)"
  }
}
table "whatsmeow_event_buffer" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "ciphertext_hash" {
    null = false
    type = bytea
  }
  column "plaintext" {
    null = true
    type = bytea
  }
  column "server_timestamp" {
    null = false
    type = bigint
  }
  column "insert_timestamp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.our_jid, column.ciphertext_hash]
  }
  foreign_key "whatsmeow_event_buffer_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsmeow_event_buffer_ciphertext_hash_check" {
    expr = "(length(ciphertext_hash) = 32)"
  }
}
table "whatsmeow_identity_keys" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "their_id" {
    null = false
    type = text
  }
  column "identity" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.our_jid, column.their_id]
  }
  foreign_key "whatsmeow_identity_keys_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsmeow_identity_keys_identity_check" {
    expr = "(length(identity) = 32)"
  }
}
table "whatsmeow_lid_map" {
  schema = schema.public
  column "lid" {
    null = false
    type = text
  }
  column "pn" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.lid]
  }
  unique "whatsmeow_lid_map_pn_key" {
    columns = [column.pn]
  }
}
table "whatsmeow_message_secrets" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "chat_jid" {
    null = false
    type = text
  }
  column "sender_jid" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "key" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.our_jid, column.chat_jid, column.sender_jid, column.message_id]
  }
  foreign_key "whatsmeow_message_secrets_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_pre_keys" {
  schema = schema.public
  column "jid" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = integer
  }
  column "key" {
    null = false
    type = bytea
  }
  column "uploaded" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.jid, column.key_id]
  }
  foreign_key "whatsmeow_pre_keys_jid_fkey" {
    columns     = [column.jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  check "whatsmeow_pre_keys_key_check" {
    expr = "(length(key) = 32)"
  }
  check "whatsmeow_pre_keys_key_id_check" {
    expr = "((key_id >= 0) AND (key_id < 16777216))"
  }
}
table "whatsmeow_privacy_tokens" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "their_jid" {
    null = false
    type = text
  }
  column "token" {
    null = false
    type = bytea
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "sender_timestamp" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.our_jid, column.their_jid]
  }
  index "idx_whatsmeow_privacy_tokens_our_jid_timestamp" {
    columns = [column.our_jid, column.timestamp]
  }
}
table "whatsmeow_retry_buffer" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "chat_jid" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "format" {
    null = false
    type = text
  }
  column "plaintext" {
    null = false
    type = bytea
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.our_jid, column.chat_jid, column.message_id]
  }
  foreign_key "whatsmeow_retry_buffer_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "whatsmeow_retry_buffer_timestamp_idx" {
    columns = [column.our_jid, column.timestamp]
  }
}
table "whatsmeow_sender_keys" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "chat_id" {
    null = false
    type = text
  }
  column "sender_id" {
    null = false
    type = text
  }
  column "sender_key" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.our_jid, column.chat_id, column.sender_id]
  }
  foreign_key "whatsmeow_sender_keys_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_sessions" {
  schema = schema.public
  column "our_jid" {
    null = false
    type = text
  }
  column "their_id" {
    null = false
    type = text
  }
  column "session" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.our_jid, column.their_id]
  }
  foreign_key "whatsmeow_sessions_our_jid_fkey" {
    columns     = [column.our_jid]
    ref_columns = [table.whatsmeow_device.column.jid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "whatsmeow_version" {
  schema = schema.public
  column "version" {
    null = true
    type = integer
  }
  column "compat" {
    null = true
    type = integer
  }
}
enum "membership" {
  schema = schema.public
  values = ["join", "leave", "invite", "ban", "knock"]
}
schema "public" {
  comment = "standard public schema"
}
