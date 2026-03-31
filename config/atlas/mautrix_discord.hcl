Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

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
table "discord_file" {
  schema = schema.public
  column "url" {
    null = false
    type = text
  }
  column "encrypted" {
    null = false
    type = boolean
  }
  column "mxc" {
    null = false
    type = text
  }
  column "id" {
    null = true
    type = text
  }
  column "emoji_name" {
    null = true
    type = text
  }
  column "size" {
    null = false
    type = bigint
  }
  column "width" {
    null = true
    type = integer
  }
  column "height" {
    null = true
    type = integer
  }
  column "mime_type" {
    null = false
    type = text
  }
  column "decryption_info" {
    null = true
    type = jsonb
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.url, column.encrypted]
  }
  index "discord_file_mxc_idx" {
    columns = [column.mxc]
  }
}
table "guild" {
  schema = schema.public
  column "dcid" {
    null = false
    type = text
  }
  column "mxid" {
    null = true
    type = text
  }
  column "plain_name" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "name_set" {
    null = false
    type = boolean
  }
  column "avatar" {
    null = false
    type = text
  }
  column "avatar_url" {
    null = false
    type = text
  }
  column "avatar_set" {
    null = false
    type = boolean
  }
  column "bridging_mode" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.dcid]
  }
  unique "guild_mxid_key" {
    columns = [column.mxid]
  }
}
table "message" {
  schema = schema.public
  column "dcid" {
    null = false
    type = text
  }
  column "dc_attachment_id" {
    null = false
    type = text
  }
  column "dc_chan_id" {
    null = false
    type = text
  }
  column "dc_chan_receiver" {
    null = false
    type = text
  }
  column "dc_sender" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "dc_edit_timestamp" {
    null = false
    type = bigint
  }
  column "dc_thread_id" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  column "sender_mxid" {
    null    = false
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.dcid, column.dc_attachment_id, column.dc_chan_id, column.dc_chan_receiver]
  }
  foreign_key "message_portal_fkey" {
    columns     = [column.dc_chan_id, column.dc_chan_receiver]
    ref_columns = [table.portal.column.dcid, table.portal.column.receiver]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "message_mxid_key" {
    columns = [column.mxid]
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
  primary_key {
    columns = [column.room_id, column.user_id]
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
  column "dcid" {
    null = false
    type = text
  }
  column "receiver" {
    null = false
    type = text
  }
  column "other_user_id" {
    null = true
    type = text
  }
  column "type" {
    null = false
    type = integer
  }
  column "dc_guild_id" {
    null = true
    type = text
  }
  column "dc_parent_id" {
    null = true
    type = text
  }
  column "dc_parent_receiver" {
    null    = false
    type    = text
    default = ""
  }
  column "mxid" {
    null = true
    type = text
  }
  column "plain_name" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "name_set" {
    null = false
    type = boolean
  }
  column "friend_nick" {
    null = false
    type = boolean
  }
  column "topic" {
    null = false
    type = text
  }
  column "topic_set" {
    null = false
    type = boolean
  }
  column "avatar" {
    null = false
    type = text
  }
  column "avatar_url" {
    null = false
    type = text
  }
  column "avatar_set" {
    null = false
    type = boolean
  }
  column "encrypted" {
    null = false
    type = boolean
  }
  column "in_space" {
    null = false
    type = text
  }
  column "first_event_id" {
    null = false
    type = text
  }
  column "relay_webhook_id" {
    null = true
    type = text
  }
  column "relay_webhook_secret" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.dcid, column.receiver]
  }
  foreign_key "portal_guild_fkey" {
    columns     = [column.dc_guild_id]
    ref_columns = [table.guild.column.dcid]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "portal_parent_fkey" {
    columns     = [column.dc_parent_id, column.dc_parent_receiver]
    ref_columns = [table.portal.column.dcid, table.portal.column.receiver]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "portal_mxid_key" {
    columns = [column.mxid]
  }
}
table "puppet" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "name_set" {
    null    = false
    type    = boolean
    default = false
  }
  column "avatar" {
    null = false
    type = text
  }
  column "avatar_url" {
    null = false
    type = text
  }
  column "avatar_set" {
    null    = false
    type    = boolean
    default = false
  }
  column "contact_info_set" {
    null    = false
    type    = boolean
    default = false
  }
  column "global_name" {
    null    = false
    type    = text
    default = ""
  }
  column "username" {
    null    = false
    type    = text
    default = ""
  }
  column "discriminator" {
    null    = false
    type    = text
    default = ""
  }
  column "is_bot" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_webhook" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_application" {
    null    = false
    type    = boolean
    default = false
  }
  column "custom_mxid" {
    null = true
    type = text
  }
  column "access_token" {
    null = true
    type = text
  }
  column "next_batch" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "reaction" {
  schema = schema.public
  column "dc_chan_id" {
    null = false
    type = text
  }
  column "dc_chan_receiver" {
    null = false
    type = text
  }
  column "dc_msg_id" {
    null = false
    type = text
  }
  column "dc_sender" {
    null = false
    type = text
  }
  column "dc_emoji_name" {
    null = false
    type = text
  }
  column "dc_thread_id" {
    null = false
    type = text
  }
  column "dc_first_attachment_id" {
    null = false
    type = text
  }
  column "mxid" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.dc_chan_id, column.dc_chan_receiver, column.dc_msg_id, column.dc_sender, column.dc_emoji_name]
  }
  foreign_key "reaction_message_fkey" {
    columns     = [column.dc_msg_id, column.dc_first_attachment_id, column.dc_chan_id, column.dc_chan_receiver]
    ref_columns = [table.message.column.dcid, table.message.column.dc_attachment_id, table.message.column.dc_chan_id, table.message.column.dc_chan_receiver]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "reaction_mxid_key" {
    columns = [column.mxid]
  }
}
table "role" {
  schema = schema.public
  column "dc_guild_id" {
    null = false
    type = text
  }
  column "dcid" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "icon" {
    null = true
    type = text
  }
  column "mentionable" {
    null = false
    type = boolean
  }
  column "managed" {
    null = false
    type = boolean
  }
  column "hoist" {
    null = false
    type = boolean
  }
  column "color" {
    null = false
    type = integer
  }
  column "position" {
    null = false
    type = integer
  }
  column "permissions" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.dc_guild_id, column.dcid]
  }
  foreign_key "role_guild_fkey" {
    columns     = [column.dc_guild_id]
    ref_columns = [table.guild.column.dcid]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "thread" {
  schema = schema.public
  column "dcid" {
    null = false
    type = text
  }
  column "parent_chan_id" {
    null = false
    type = text
  }
  column "root_msg_dcid" {
    null = false
    type = text
  }
  column "root_msg_mxid" {
    null = false
    type = text
  }
  column "creation_notice_mxid" {
    null = false
    type = text
  }
  column "receiver" {
    null    = false
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.dcid]
  }
  foreign_key "thread_parent_fkey" {
    columns     = [column.parent_chan_id, column.receiver]
    ref_columns = [table.portal.column.dcid, table.portal.column.receiver]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "user" {
  schema = schema.public
  column "mxid" {
    null = false
    type = text
  }
  column "dcid" {
    null = true
    type = text
  }
  column "discord_token" {
    null = true
    type = text
  }
  column "management_room" {
    null = true
    type = text
  }
  column "space_room" {
    null = true
    type = text
  }
  column "dm_space_room" {
    null = true
    type = text
  }
  column "read_state_version" {
    null    = false
    type    = integer
    default = 0
  }
  column "heartbeat_session" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.mxid]
  }
  unique "user_dcid_key" {
    columns = [column.dcid]
  }
}
table "user_portal" {
  schema = schema.public
  column "discord_id" {
    null = false
    type = text
  }
  column "user_mxid" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "in_space" {
    null = false
    type = boolean
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.discord_id, column.user_mxid]
  }
  foreign_key "up_user_fkey" {
    columns     = [column.user_mxid]
    ref_columns = [table.user.column.mxid]
    on_update   = NO_ACTION
    on_delete   = CASCADE
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
enum "membership" {
  schema = schema.public
  values = ["join", "leave", "invite", "ban", "knock"]
}
schema "public" {
  comment = "standard public schema"
}
