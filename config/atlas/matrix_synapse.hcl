Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "access_tokens" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = true
    type = text
  }
  column "token" {
    null = false
    type = text
  }
  column "valid_until_ms" {
    null = true
    type = bigint
  }
  column "puppets_user_id" {
    null = true
    type = text
  }
  column "last_validated" {
    null = true
    type = bigint
  }
  column "refresh_token_id" {
    null = true
    type = bigint
  }
  column "used" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "access_tokens_refresh_token_id_fkey" {
    columns     = [column.refresh_token_id]
    ref_columns = [table.refresh_tokens.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "access_tokens_device_id" {
    columns = [column.user_id, column.device_id]
  }
  index "access_tokens_refresh_token_id_idx" {
    columns = [column.refresh_token_id]
  }
  unique "access_tokens_token_key" {
    columns = [column.token]
  }
}
table "account_data" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "account_data_type" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "content" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "account_data_stream_id" {
    columns = [column.user_id, column.stream_id]
  }
  unique "account_data_uniqueness" {
    columns = [column.user_id, column.account_data_type]
  }
}
table "account_validity" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "expiration_ts_ms" {
    null = false
    type = bigint
  }
  column "email_sent" {
    null = false
    type = boolean
  }
  column "renewal_token" {
    null = true
    type = text
  }
  column "token_used_ts_ms" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.user_id]
  }
}
table "application_services_state" {
  schema = schema.public
  column "as_id" {
    null = false
    type = text
  }
  column "state" {
    null = true
    type = character_varying(5)
  }
  column "read_receipt_stream_id" {
    null = true
    type = bigint
  }
  column "presence_stream_id" {
    null = true
    type = bigint
  }
  column "to_device_stream_id" {
    null = true
    type = bigint
  }
  column "device_list_stream_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.as_id]
  }
}
table "application_services_txns" {
  schema = schema.public
  column "as_id" {
    null = false
    type = text
  }
  column "txn_id" {
    null = false
    type = bigint
  }
  column "event_ids" {
    null = false
    type = text
  }
  index "application_services_txns_id" {
    columns = [column.as_id]
  }
  unique "application_services_txns_as_id_txn_id_key" {
    columns = [column.as_id, column.txn_id]
  }
}
table "applied_module_schemas" {
  schema = schema.public
  column "module_name" {
    null = false
    type = text
  }
  column "file" {
    null = false
    type = text
  }
  unique "applied_module_schemas_module_name_file_key" {
    columns = [column.module_name, column.file]
  }
}
table "applied_schema_deltas" {
  schema = schema.public
  column "version" {
    null = false
    type = integer
  }
  column "file" {
    null = false
    type = text
  }
  unique "applied_schema_deltas_version_file_key" {
    columns = [column.version, column.file]
  }
}
table "appservice_room_list" {
  schema = schema.public
  column "appservice_id" {
    null = false
    type = text
  }
  column "network_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  index "appservice_room_list_idx" {
    unique  = true
    columns = [column.appservice_id, column.network_id, column.room_id]
  }
}
table "appservice_stream_position" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_ordering" {
    null = true
    type = bigint
  }
  check "appservice_stream_position_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "appservice_stream_position_lock_key" {
    columns = [column.lock]
  }
}
table "background_updates" {
  schema = schema.public
  column "update_name" {
    null = false
    type = text
  }
  column "progress_json" {
    null = false
    type = text
  }
  column "depends_on" {
    null = true
    type = text
  }
  column "ordering" {
    null    = false
    type    = integer
    default = 0
  }
  unique "background_updates_uniqueness" {
    columns = [column.update_name]
  }
}
table "blocked_rooms" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  index "blocked_rooms_idx" {
    unique  = true
    columns = [column.room_id]
  }
}
table "cache_invalidation_stream_by_instance" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "cache_func" {
    null = false
    type = text
  }
  column "keys" {
    null = true
    type = sql("text[]")
  }
  column "invalidation_ts" {
    null = true
    type = bigint
  }
  index "cache_invalidation_stream_by_instance_id" {
    unique  = true
    columns = [column.stream_id]
  }
  index "cache_invalidation_stream_by_instance_instance_index" {
    columns = [column.instance_name, column.stream_id]
  }
}
table "current_state_delta_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "state_key" {
    null = false
    type = text
  }
  column "event_id" {
    null = true
    type = text
  }
  column "prev_event_id" {
    null = true
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "current_state_delta_stream_idx" {
    columns = [column.stream_id]
  }
  index "current_state_delta_stream_room_idx" {
    columns = [column.room_id, column.stream_id]
  }
}
table "current_state_events" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "state_key" {
    null = false
    type = text
  }
  column "membership" {
    null = true
    type = text
  }
  column "event_stream_ordering" {
    null = true
    type = bigint
  }
  foreign_key "event_stream_ordering_fkey" {
    columns     = [column.event_stream_ordering]
    ref_columns = [table.events.column.stream_ordering]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "current_state_events_member_index" {
    columns = [column.state_key]
    where   = "(type = 'm.room.member'::text)"
  }
  index "current_state_events_members_room_index" {
    columns = [column.room_id, column.membership]
    where   = "(type = 'm.room.member'::text)"
  }
  index "current_state_events_stream_ordering_idx" {
    columns = [column.event_stream_ordering]
  }
  unique "current_state_events_event_id_key" {
    columns = [column.event_id]
  }
  unique "current_state_events_room_id_type_state_key_key" {
    columns = [column.room_id, column.type, column.state_key]
  }
}
table "dehydrated_devices" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "device_data" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.user_id]
  }
}
table "delayed_events" {
  schema = schema.public
  column "delay_id" {
    null = false
    type = text
  }
  column "user_localpart" {
    null = false
    type = text
  }
  column "device_id" {
    null = true
    type = text
  }
  column "delay" {
    null = false
    type = bigint
  }
  column "send_ts" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_type" {
    null = false
    type = text
  }
  column "state_key" {
    null = true
    type = text
  }
  column "origin_server_ts" {
    null = true
    type = bigint
  }
  column "content" {
    null = false
    type = text
  }
  column "is_processed" {
    null    = false
    type    = boolean
    default = false
  }
  column "sticky_duration_ms" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.user_localpart, column.delay_id]
  }
  index "delayed_events_idx" {
    unique  = true
    columns = [column.delay_id]
  }
  index "delayed_events_is_processed" {
    columns = [column.is_processed]
  }
  index "delayed_events_room_state_event_idx" {
    columns = [column.room_id, column.event_type, column.state_key]
    where   = "(state_key IS NOT NULL)"
  }
  index "delayed_events_send_ts" {
    columns = [column.send_ts]
  }
}
table "delayed_events_stream_pos" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  check "delayed_events_stream_pos_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "delayed_events_stream_pos_lock_key" {
    columns = [column.lock]
  }
}
table "deleted_pushers" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "app_id" {
    null = false
    type = text
  }
  column "pushkey" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "deleted_pushers_stream_id" {
    columns = [column.stream_id]
  }
}
table "destination_rooms" {
  schema  = schema.public
  comment = "Information about transmission of PDUs in a given room to a given remote homeserver."
  column "destination" {
    null    = false
    type    = text
    comment = "server name of remote homeserver in question"
  }
  column "room_id" {
    null    = false
    type    = text
    comment = "room ID in question"
  }
  column "stream_ordering" {
    null    = false
    type    = bigint
    comment = "`stream_ordering` of the most recent PDU in this room that needs to be sent (by us) to this homeserver.\nThis can only be pointing to our own PDU because we are only responsible for sending our own PDUs."
  }
  primary_key {
    columns = [column.destination, column.room_id]
  }
  foreign_key "destination_rooms_destination_fkey" {
    columns     = [column.destination]
    ref_columns = [table.destinations.column.destination]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "destination_rooms_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "destination_rooms_room_id" {
    columns = [column.room_id]
  }
}
table "destinations" {
  schema  = schema.public
  comment = "Information about remote homeservers and the health of our connection to them."
  column "destination" {
    null    = false
    type    = text
    comment = "server name of remote homeserver in question"
  }
  column "retry_last_ts" {
    null    = true
    type    = bigint
    comment = "The last time we tried and failed to reach the remote server, in ms.\nThis field is reset to `0` when we succeed in connecting again."
  }
  column "retry_interval" {
    null    = true
    type    = bigint
    comment = "How long, in milliseconds, to wait since the last time we tried to reach the remote server before trying again.\nThis field is reset to `0` when we succeed in connecting again."
  }
  column "failure_ts" {
    null    = true
    type    = bigint
    comment = "The first time we tried and failed to reach the remote server, in ms.\nThis field is reset to `NULL` when we succeed in connecting again."
  }
  column "last_successful_stream_ordering" {
    null    = true
    type    = bigint
    comment = "Stream ordering of the most recently successfully sent PDU to this server, sent through normal send (not e.g. backfill).\nIn Catch-Up Mode, the original PDU persisted by us is represented here, even if we sent a later forward extremity in its stead.\nSee `destination_rooms` for more information about catch-up."
  }
  primary_key {
    columns = [column.destination]
  }
}
table "device_auth_providers" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "auth_provider_id" {
    null = false
    type = text
  }
  column "auth_provider_session_id" {
    null = false
    type = text
  }
  index "device_auth_providers_devices" {
    columns = [column.user_id, column.device_id]
  }
  index "device_auth_providers_sessions" {
    columns = [column.auth_provider_id, column.auth_provider_session_id]
  }
}
table "device_federation_inbox" {
  schema = schema.public
  column "origin" {
    null = false
    type = text
  }
  column "message_id" {
    null = false
    type = text
  }
  column "received_ts" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_federation_inbox_received_ts_index" {
    columns = [column.received_ts]
  }
  index "device_federation_inbox_sender_id" {
    columns = [column.origin, column.message_id]
  }
}
table "device_federation_outbox" {
  schema = schema.public
  column "destination" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "queued_ts" {
    null = false
    type = bigint
  }
  column "messages_json" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_federation_outbox_destination_id" {
    columns = [column.destination, column.stream_id]
  }
  index "device_federation_outbox_id" {
    columns = [column.stream_id]
  }
}
table "device_inbox" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "message_json" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_inbox_stream_id_user_id" {
    columns = [column.stream_id, column.user_id]
  }
  index "device_inbox_user_stream_id" {
    columns = [column.user_id, column.device_id, column.stream_id]
  }
}
table "device_lists_changes_converted_stream_position" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  check "device_lists_changes_converted_stream_position_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "device_lists_changes_converted_stream_position_lock_key" {
    columns = [column.lock]
  }
}
table "device_lists_changes_in_room" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "converted_to_destinations" {
    null = false
    type = boolean
  }
  column "opentracing_context" {
    null = true
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_lists_changes_in_room_by_room_idx" {
    columns = [column.room_id, column.stream_id]
  }
  index "device_lists_changes_in_stream_id" {
    unique  = true
    columns = [column.stream_id, column.room_id]
  }
  index "device_lists_changes_in_stream_id_unconverted" {
    columns = [column.stream_id]
    where   = "(NOT converted_to_destinations)"
  }
}
table "device_lists_outbound_last_success" {
  schema = schema.public
  column "destination" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  index "device_lists_outbound_last_success_unique_idx" {
    unique  = true
    columns = [column.destination, column.user_id]
  }
}
table "device_lists_outbound_pokes" {
  schema = schema.public
  column "destination" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "sent" {
    null = false
    type = boolean
  }
  column "ts" {
    null = false
    type = bigint
  }
  column "opentracing_context" {
    null = true
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_lists_outbound_pokes_id" {
    columns = [column.destination, column.stream_id]
  }
  index "device_lists_outbound_pokes_stream" {
    columns = [column.stream_id]
  }
  index "device_lists_outbound_pokes_user" {
    columns = [column.destination, column.user_id]
  }
}
table "device_lists_remote_cache" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "content" {
    null = false
    type = text
  }
  index "device_lists_remote_cache_unique_id" {
    unique  = true
    columns = [column.user_id, column.device_id]
  }
}
table "device_lists_remote_extremeties" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = text
  }
  index "device_lists_remote_extremeties_unique_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "device_lists_remote_pending" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.stream_id]
  }
  index "device_lists_remote_pending_user_device_id" {
    unique  = true
    columns = [column.user_id, column.device_id]
  }
}
table "device_lists_remote_resync" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "added_ts" {
    null = false
    type = bigint
  }
  index "device_lists_remote_resync_idx" {
    unique  = true
    columns = [column.user_id]
  }
  index "device_lists_remote_resync_ts_idx" {
    columns = [column.added_ts]
  }
}
table "device_lists_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "device_lists_stream_id" {
    columns = [column.stream_id, column.user_id]
  }
  index "device_lists_stream_user_id" {
    columns = [column.user_id, column.device_id]
  }
}
table "devices" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "display_name" {
    null = true
    type = text
  }
  column "last_seen" {
    null = true
    type = bigint
  }
  column "ip" {
    null = true
    type = text
  }
  column "user_agent" {
    null = true
    type = text
  }
  column "hidden" {
    null    = true
    type    = boolean
    default = false
  }
  unique "device_uniqueness" {
    columns = [column.user_id, column.device_id]
  }
}
table "e2e_cross_signing_keys" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "keytype" {
    null = false
    type = text
  }
  column "keydata" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "updatable_without_uia_before_ms" {
    null = true
    type = bigint
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "e2e_cross_signing_keys_idx" {
    unique  = true
    columns = [column.user_id, column.keytype, column.stream_id]
  }
  index "e2e_cross_signing_keys_stream_idx" {
    unique  = true
    columns = [column.stream_id]
  }
}
table "e2e_cross_signing_signatures" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = text
  }
  column "target_user_id" {
    null = false
    type = text
  }
  column "target_device_id" {
    null = false
    type = text
  }
  column "signature" {
    null = false
    type = text
  }
  index "e2e_cross_signing_signatures2_idx" {
    columns = [column.user_id, column.target_user_id, column.target_device_id]
  }
}
table "e2e_device_keys_json" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "ts_added_ms" {
    null = false
    type = bigint
  }
  column "key_json" {
    null = false
    type = text
  }
  unique "e2e_device_keys_json_uniqueness" {
    columns = [column.user_id, column.device_id]
  }
}
table "e2e_fallback_keys_json" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "algorithm" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = text
  }
  column "key_json" {
    null = false
    type = text
  }
  column "used" {
    null    = false
    type    = boolean
    default = false
  }
  unique "e2e_fallback_keys_json_uniqueness" {
    columns = [column.user_id, column.device_id, column.algorithm]
  }
}
table "e2e_one_time_keys_json" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "algorithm" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = text
  }
  column "ts_added_ms" {
    null = false
    type = bigint
  }
  column "key_json" {
    null = false
    type = text
  }
  index "e2e_one_time_keys_json_user_id_device_id_algorithm_ts_added_idx" {
    columns = [column.user_id, column.device_id, column.algorithm, column.ts_added_ms]
  }
  unique "e2e_one_time_keys_json_uniqueness" {
    columns = [column.user_id, column.device_id, column.algorithm, column.key_id]
  }
}
table "e2e_room_keys" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "session_id" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = bigint
  }
  column "first_message_index" {
    null = true
    type = integer
  }
  column "forwarded_count" {
    null = true
    type = integer
  }
  column "is_verified" {
    null = true
    type = boolean
  }
  column "session_data" {
    null = false
    type = text
  }
  index "e2e_room_keys_room_id" {
    columns = [column.room_id]
  }
  index "e2e_room_keys_with_version_idx" {
    unique  = true
    columns = [column.user_id, column.version, column.room_id, column.session_id]
  }
}
table "e2e_room_keys_versions" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = bigint
  }
  column "algorithm" {
    null = false
    type = text
  }
  column "auth_data" {
    null = false
    type = text
  }
  column "deleted" {
    null    = false
    type    = smallint
    default = 0
  }
  column "etag" {
    null = true
    type = bigint
  }
  index "e2e_room_keys_versions_idx" {
    unique  = true
    columns = [column.user_id, column.version]
  }
}
table "erased_users" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  index "erased_users_user" {
    unique  = true
    columns = [column.user_id]
  }
}
table "event_auth" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "auth_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  index "evauth_edges_id" {
    columns = [column.event_id]
  }
}
table "event_auth_chain_links" {
  schema = schema.public
  column "origin_chain_id" {
    null = false
    type = bigint
  }
  column "origin_sequence_number" {
    null = false
    type = bigint
  }
  column "target_chain_id" {
    null = false
    type = bigint
  }
  column "target_sequence_number" {
    null = false
    type = bigint
  }
  index "event_auth_chain_links_idx" {
    columns = [column.origin_chain_id, column.target_chain_id]
  }
  index "event_auth_chain_links_origin_index" {
    columns = [column.origin_chain_id, column.origin_sequence_number]
  }
}
table "event_auth_chain_to_calculate" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "state_key" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.event_id]
  }
  index "event_auth_chain_to_calculate_rm_id" {
    columns = [column.room_id]
  }
}
table "event_auth_chains" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "chain_id" {
    null = false
    type = bigint
  }
  column "sequence_number" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.event_id]
  }
  index "event_auth_chains_c_seq_index" {
    unique  = true
    columns = [column.chain_id, column.sequence_number]
  }
}
table "event_backward_extremities" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  index "ev_b_extrem_id" {
    columns = [column.event_id]
  }
  index "ev_b_extrem_room" {
    columns = [column.room_id]
  }
  unique "event_backward_extremities_event_id_room_id_key" {
    columns = [column.event_id, column.room_id]
  }
}
table "event_edges" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "prev_event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = true
    type = text
  }
  column "is_state" {
    null    = false
    type    = boolean
    default = false
  }
  foreign_key "event_edges_event_id_fkey" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ev_edges_prev_id" {
    columns = [column.prev_event_id]
  }
  index "event_edges_event_id_prev_event_id_idx" {
    unique  = true
    columns = [column.event_id, column.prev_event_id]
  }
}
table "event_expiry" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "expiry_ts" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.event_id]
  }
  index "event_expiry_expiry_ts_idx" {
    columns = [column.expiry_ts]
  }
}
table "event_failed_pull_attempts" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "num_attempts" {
    null = false
    type = integer
  }
  column "last_attempt_ts" {
    null = false
    type = bigint
  }
  column "last_cause" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.room_id, column.event_id]
  }
  foreign_key "event_failed_pull_attempts_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "event_failed_pull_attempts_room_id" {
    columns = [column.room_id]
  }
}
table "event_forward_extremities" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  foreign_key "event_forward_extremities_event_id" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ev_extrem_id" {
    columns = [column.event_id]
  }
  index "ev_extrem_room" {
    columns = [column.room_id]
  }
  unique "event_forward_extremities_event_id_room_id_key" {
    columns = [column.event_id, column.room_id]
  }
}
table "event_json" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "internal_metadata" {
    null = false
    type = text
  }
  column "json" {
    null = false
    type = text
  }
  column "format_version" {
    null = true
    type = integer
  }
  unique "event_json_event_id_key" {
    columns = [column.event_id]
  }
}
table "event_labels" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "label" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "topological_ordering" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.event_id, column.label]
  }
  index "event_labels_room_id_label_idx" {
    columns = [column.room_id, column.label, column.topological_ordering]
  }
}
table "event_push_actions" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "profile_tag" {
    null = true
    type = character_varying(32)
  }
  column "actions" {
    null = false
    type = text
  }
  column "topological_ordering" {
    null = true
    type = bigint
  }
  column "stream_ordering" {
    null = true
    type = bigint
  }
  column "notif" {
    null = true
    type = smallint
  }
  column "highlight" {
    null = true
    type = smallint
  }
  column "unread" {
    null = true
    type = smallint
  }
  column "thread_id" {
    null = true
    type = text
  }
  index "event_push_actions_highlights_index" {
    columns = [column.user_id, column.room_id, column.topological_ordering, column.stream_ordering]
    where   = "(highlight = 1)"
  }
  index "event_push_actions_rm_tokens" {
    columns = [column.user_id, column.room_id, column.topological_ordering, column.stream_ordering]
  }
  index "event_push_actions_room_id_user_id" {
    columns = [column.room_id, column.user_id]
  }
  index "event_push_actions_stream_highlight_index" {
    columns = [column.highlight, column.stream_ordering]
    where   = "(highlight = 0)"
  }
  index "event_push_actions_stream_ordering" {
    columns = [column.stream_ordering, column.user_id]
  }
  index "event_push_actions_u_highlight" {
    columns = [column.user_id, column.stream_ordering]
  }
  check "event_push_actions_thread_id" {
    expr = "(thread_id IS NOT NULL)"
  }
  unique "event_id_user_id_profile_tag_uniqueness" {
    columns = [column.room_id, column.event_id, column.user_id, column.profile_tag]
  }
}
table "event_push_actions_staging" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "actions" {
    null = false
    type = text
  }
  column "notif" {
    null = false
    type = smallint
  }
  column "highlight" {
    null = false
    type = smallint
  }
  column "unread" {
    null = true
    type = smallint
  }
  column "thread_id" {
    null = true
    type = text
  }
  column "inserted_ts" {
    null    = true
    type    = bigint
    default = sql("(EXTRACT(epoch FROM now()) * (1000)::numeric)")
  }
  index "event_push_actions_staging_id" {
    columns = [column.event_id]
  }
  check "event_push_actions_staging_thread_id" {
    expr = "(thread_id IS NOT NULL)"
  }
}
table "event_push_summary" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "notif_count" {
    null = false
    type = bigint
  }
  column "stream_ordering" {
    null = false
    type = bigint
  }
  column "unread_count" {
    null = true
    type = bigint
  }
  column "last_receipt_stream_ordering" {
    null = true
    type = bigint
  }
  column "thread_id" {
    null = true
    type = text
  }
  index "event_push_summary_index_room_id" {
    columns = [column.room_id]
  }
  index "event_push_summary_unique_index2" {
    unique  = true
    columns = [column.user_id, column.room_id, column.thread_id]
  }
  check "event_push_summary_thread_id" {
    expr = "(thread_id IS NOT NULL)"
  }
}
table "event_push_summary_last_receipt_stream_id" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  check "event_push_summary_last_receipt_stream_id_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "event_push_summary_last_receipt_stream_id_lock_key" {
    columns = [column.lock]
  }
}
table "event_push_summary_stream_ordering" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_ordering" {
    null = false
    type = bigint
  }
  check "event_push_summary_stream_ordering_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "event_push_summary_stream_ordering_lock_key" {
    columns = [column.lock]
  }
}
table "event_relations" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "relates_to_id" {
    null = false
    type = text
  }
  column "relation_type" {
    null = false
    type = text
  }
  column "aggregation_key" {
    null = true
    type = text
  }
  index "event_relations_id" {
    unique  = true
    columns = [column.event_id]
  }
  index "event_relations_relates" {
    columns = [column.relates_to_id, column.relation_type, column.aggregation_key]
  }
}
table "event_reports" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "received_ts" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "reason" {
    null = true
    type = text
  }
  column "content" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "event_search" {
  schema = schema.public
  column "event_id" {
    null = true
    type = text
  }
  column "room_id" {
    null = true
    type = text
  }
  column "sender" {
    null = true
    type = text
  }
  column "key" {
    null = true
    type = text
  }
  column "vector" {
    null = true
    type = tsvector
  }
  column "origin_server_ts" {
    null = true
    type = bigint
  }
  column "stream_ordering" {
    null = true
    type = bigint
  }
  index "event_search_ev_ridx" {
    columns = [column.room_id]
  }
  index "event_search_event_id_idx" {
    unique  = true
    columns = [column.event_id]
  }
  index "event_search_fts_idx" {
    columns = [column.vector]
    type    = GIN
  }
}
table "event_to_state_groups" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "state_group" {
    null = false
    type = bigint
  }
  index "event_to_state_groups_sg_index" {
    columns = [column.state_group]
  }
  unique "event_to_state_groups_event_id_key" {
    columns = [column.event_id]
  }
}
table "event_txn_id_device_id" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "txn_id" {
    null = false
    type = text
  }
  column "inserted_ts" {
    null = false
    type = bigint
  }
  foreign_key "event_txn_id_device_id_event_id_fkey" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "event_txn_id_device_id_user_id_device_id_fkey" {
    columns     = [column.user_id, column.device_id]
    ref_columns = [table.devices.column.user_id, table.devices.column.device_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "event_txn_id_device_id_event_id" {
    unique  = true
    columns = [column.event_id]
  }
  index "event_txn_id_device_id_ts" {
    columns = [column.inserted_ts]
  }
  index "event_txn_id_device_id_txn_id2" {
    unique  = true
    columns = [column.user_id, column.device_id, column.room_id, column.txn_id]
  }
}
table "events" {
  schema = schema.public
  column "topological_ordering" {
    null = false
    type = bigint
  }
  column "event_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "content" {
    null = true
    type = text
  }
  column "unrecognized_keys" {
    null = true
    type = text
  }
  column "processed" {
    null = false
    type = boolean
  }
  column "outlier" {
    null = false
    type = boolean
  }
  column "depth" {
    null    = false
    type    = bigint
    default = 0
  }
  column "origin_server_ts" {
    null = true
    type = bigint
  }
  column "received_ts" {
    null = true
    type = bigint
  }
  column "sender" {
    null = true
    type = text
  }
  column "contains_url" {
    null = true
    type = boolean
  }
  column "instance_name" {
    null = true
    type = text
  }
  column "stream_ordering" {
    null = true
    type = bigint
  }
  column "state_key" {
    null = true
    type = text
  }
  column "rejection_reason" {
    null = true
    type = text
  }
  index "event_contains_url_index" {
    columns = [column.room_id, column.topological_ordering, column.stream_ordering]
    where   = "((contains_url = true) AND (outlier = false))"
  }
  index "events_jump_to_date_idx" {
    columns = [column.room_id, column.origin_server_ts]
    where   = "(NOT outlier)"
  }
  index "events_order_room" {
    columns = [column.room_id, column.topological_ordering, column.stream_ordering]
  }
  index "events_room_stream" {
    columns = [column.room_id, column.stream_ordering]
  }
  index "events_stream_ordering" {
    unique  = true
    columns = [column.stream_ordering]
  }
  index "events_ts" {
    columns = [column.origin_server_ts, column.stream_ordering]
  }
  index "received_ts_idx" {
    columns = [column.received_ts]
    where   = "(type = 'm.room.member'::text)"
  }
  unique "events_event_id_key" {
    columns = [column.event_id]
  }
}
table "ex_outlier_stream" {
  schema = schema.public
  column "event_stream_ordering" {
    null = false
    type = bigint
  }
  column "event_id" {
    null = false
    type = text
  }
  column "state_group" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.event_stream_ordering]
  }
}
table "federation_inbound_events_staging" {
  schema = schema.public
  column "origin" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "received_ts" {
    null = false
    type = bigint
  }
  column "event_json" {
    null = false
    type = text
  }
  column "internal_metadata" {
    null = false
    type = text
  }
  index "federation_inbound_events_staging_instance_event" {
    unique  = true
    columns = [column.origin, column.event_id]
  }
  index "federation_inbound_events_staging_room" {
    columns = [column.room_id, column.received_ts]
  }
}
table "federation_stream_position" {
  schema = schema.public
  column "type" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null    = false
    type    = text
    default = "master"
  }
  index "federation_stream_position_instance" {
    unique  = true
    columns = [column.type, column.instance_name]
  }
}
table "ignored_users" {
  schema = schema.public
  column "ignorer_user_id" {
    null = false
    type = text
  }
  column "ignored_user_id" {
    null = false
    type = text
  }
  index "ignored_users_ignored_user_id" {
    columns = [column.ignored_user_id]
  }
  index "ignored_users_uniqueness" {
    unique  = true
    columns = [column.ignorer_user_id, column.ignored_user_id]
  }
}
table "instance_map" {
  schema = schema.public
  column "instance_id" {
    null = false
    type = serial
  }
  column "instance_name" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.instance_id]
  }
  index "instance_map_idx" {
    unique  = true
    columns = [column.instance_name]
  }
}
table "local_current_membership" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "membership" {
    null = false
    type = text
  }
  column "event_stream_ordering" {
    null = true
    type = bigint
  }
  foreign_key "event_stream_ordering_fkey" {
    columns     = [column.event_stream_ordering]
    ref_columns = [table.events.column.stream_ordering]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "local_current_membership_idx" {
    unique  = true
    columns = [column.user_id, column.room_id]
  }
  index "local_current_membership_room_idx" {
    columns = [column.room_id]
  }
  index "local_current_membership_stream_ordering_idx" {
    columns = [column.event_stream_ordering]
  }
}
table "local_media_repository" {
  schema = schema.public
  column "media_id" {
    null = true
    type = text
  }
  column "media_type" {
    null = true
    type = text
  }
  column "media_length" {
    null = true
    type = integer
  }
  column "created_ts" {
    null = true
    type = bigint
  }
  column "upload_name" {
    null = true
    type = text
  }
  column "user_id" {
    null = true
    type = text
  }
  column "quarantined_by" {
    null = true
    type = text
  }
  column "url_cache" {
    null = true
    type = text
  }
  column "last_access_ts" {
    null = true
    type = bigint
  }
  column "safe_from_quarantine" {
    null    = false
    type    = boolean
    default = false
  }
  column "authenticated" {
    null    = false
    type    = boolean
    default = false
  }
  column "sha256" {
    null = true
    type = text
  }
  index "local_media_repository_sha256" {
    columns = [column.sha256]
    where   = "(sha256 IS NOT NULL)"
  }
  index "local_media_repository_url_idx" {
    columns = [column.created_ts]
    where   = "(url_cache IS NOT NULL)"
  }
  index "users_have_local_media" {
    columns = [column.user_id, column.created_ts]
  }
  unique "local_media_repository_media_id_key" {
    columns = [column.media_id]
  }
}
table "local_media_repository_thumbnails" {
  schema = schema.public
  column "media_id" {
    null = true
    type = text
  }
  column "thumbnail_width" {
    null = true
    type = integer
  }
  column "thumbnail_height" {
    null = true
    type = integer
  }
  column "thumbnail_type" {
    null = true
    type = text
  }
  column "thumbnail_method" {
    null = true
    type = text
  }
  column "thumbnail_length" {
    null = true
    type = integer
  }
  index "local_media_repository_thumbn_media_id_width_height_method_key" {
    unique  = true
    columns = [column.media_id, column.thumbnail_width, column.thumbnail_height, column.thumbnail_type, column.thumbnail_method]
  }
  index "local_media_repository_thumbnails_media_id" {
    columns = [column.media_id]
  }
}
table "local_media_repository_url_cache" {
  schema = schema.public
  column "url" {
    null = true
    type = text
  }
  column "response_code" {
    null = true
    type = integer
  }
  column "etag" {
    null = true
    type = text
  }
  column "expires_ts" {
    null = true
    type = bigint
  }
  column "og" {
    null = true
    type = text
  }
  column "media_id" {
    null = true
    type = text
  }
  column "download_ts" {
    null = true
    type = bigint
  }
  index "local_media_repository_url_cache_by_url_download_ts" {
    columns = [column.url, column.download_ts]
  }
  index "local_media_repository_url_cache_expires_idx" {
    columns = [column.expires_ts]
  }
  index "local_media_repository_url_cache_media_idx" {
    columns = [column.media_id]
  }
}
table "login_tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "expiry_ts" {
    null = false
    type = bigint
  }
  column "used_ts" {
    null = true
    type = bigint
  }
  column "auth_provider_id" {
    null = true
    type = text
  }
  column "auth_provider_session_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.token]
  }
  index "login_tokens_auth_provider_idx" {
    columns = [column.auth_provider_id, column.auth_provider_session_id]
  }
  index "login_tokens_expiry_time_idx" {
    columns = [column.expiry_ts]
  }
}
table "monthly_active_users" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  index "monthly_active_users_time_stamp" {
    columns = [column.timestamp]
  }
  index "monthly_active_users_users" {
    unique  = true
    columns = [column.user_id]
  }
}
table "open_id_tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = text
  }
  column "ts_valid_until_ms" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.token]
  }
  index "open_id_tokens_ts_valid_until_ms" {
    columns = [column.ts_valid_until_ms]
  }
}
table "partial_state_events" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  foreign_key "partial_state_events_event_id_fkey" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "partial_state_events_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.partial_state_rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "partial_state_events_room_id_idx" {
    columns = [column.room_id]
  }
  unique "partial_state_events_event_id_key" {
    columns = [column.event_id]
  }
}
table "partial_state_rooms" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "device_lists_stream_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "join_event_id" {
    null = true
    type = text
  }
  column "joined_via" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.room_id]
  }
  foreign_key "partial_state_rooms_join_event_id_fkey" {
    columns     = [column.join_event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "partial_state_rooms_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "partial_state_rooms_servers" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "server_name" {
    null = false
    type = text
  }
  foreign_key "partial_state_rooms_servers_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.partial_state_rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "partial_state_rooms_servers_room_id_server_name_key" {
    columns = [column.room_id, column.server_name]
  }
}
table "per_user_experimental_features" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "feature" {
    null = false
    type = text
  }
  column "enabled" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.user_id, column.feature]
  }
  foreign_key "per_user_experimental_features_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.name]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "presence_stream" {
  schema = schema.public
  column "stream_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = true
    type = text
  }
  column "state" {
    null = true
    type = text
  }
  column "last_active_ts" {
    null = true
    type = bigint
  }
  column "last_federation_update_ts" {
    null = true
    type = bigint
  }
  column "last_user_sync_ts" {
    null = true
    type = bigint
  }
  column "status_msg" {
    null = true
    type = text
  }
  column "currently_active" {
    null = true
    type = boolean
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "presence_stream_id" {
    columns = [column.stream_id, column.user_id]
  }
  index "presence_stream_state_not_offline_idx" {
    columns = [column.state]
    where   = "(state <> 'offline'::text)"
  }
  index "presence_stream_user_id" {
    columns = [column.user_id]
  }
}
table "profiles" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "displayname" {
    null = true
    type = text
  }
  column "avatar_url" {
    null = true
    type = text
  }
  column "full_user_id" {
    null = true
    type = text
  }
  column "fields" {
    null = true
    type = jsonb
  }
  index "profiles_full_user_id_key" {
    unique  = true
    columns = [column.full_user_id]
  }
  check "full_user_id_not_null" {
    expr = "(full_user_id IS NOT NULL)"
  }
  unique "profiles_user_id_key" {
    columns = [column.user_id]
  }
}
table "push_rules" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "user_name" {
    null = false
    type = text
  }
  column "rule_id" {
    null = false
    type = text
  }
  column "priority_class" {
    null = false
    type = smallint
  }
  column "priority" {
    null    = false
    type    = integer
    default = 0
  }
  column "conditions" {
    null = false
    type = text
  }
  column "actions" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "push_rules_user_name" {
    columns = [column.user_name]
  }
  unique "push_rules_user_name_rule_id_key" {
    columns = [column.user_name, column.rule_id]
  }
}
table "push_rules_enable" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "user_name" {
    null = false
    type = text
  }
  column "rule_id" {
    null = false
    type = text
  }
  column "enabled" {
    null = true
    type = smallint
  }
  primary_key {
    columns = [column.id]
  }
  index "push_rules_enable_user_name" {
    columns = [column.user_name]
  }
  unique "push_rules_enable_user_name_rule_id_key" {
    columns = [column.user_name, column.rule_id]
  }
}
table "push_rules_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "event_stream_ordering" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "rule_id" {
    null = false
    type = text
  }
  column "op" {
    null = false
    type = text
  }
  column "priority_class" {
    null = true
    type = smallint
  }
  column "priority" {
    null = true
    type = integer
  }
  column "conditions" {
    null = true
    type = text
  }
  column "actions" {
    null = true
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "push_rules_stream_id" {
    columns = [column.stream_id]
  }
  index "push_rules_stream_user_stream_id" {
    columns = [column.user_id, column.stream_id]
  }
}
table "pusher_throttle" {
  schema = schema.public
  column "pusher" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "last_sent_ts" {
    null = true
    type = bigint
  }
  column "throttle_ms" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.pusher, column.room_id]
  }
}
table "pushers" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "user_name" {
    null = false
    type = text
  }
  column "access_token" {
    null = true
    type = bigint
  }
  column "profile_tag" {
    null = false
    type = text
  }
  column "kind" {
    null = false
    type = text
  }
  column "app_id" {
    null = false
    type = text
  }
  column "app_display_name" {
    null = false
    type = text
  }
  column "device_display_name" {
    null = false
    type = text
  }
  column "pushkey" {
    null = false
    type = text
  }
  column "ts" {
    null = false
    type = bigint
  }
  column "lang" {
    null = true
    type = text
  }
  column "data" {
    null = true
    type = text
  }
  column "last_stream_ordering" {
    null = true
    type = bigint
  }
  column "last_success" {
    null = true
    type = bigint
  }
  column "failing_since" {
    null = true
    type = bigint
  }
  column "enabled" {
    null = true
    type = boolean
  }
  column "device_id" {
    null = true
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  unique "pushers2_app_id_pushkey_user_name_key" {
    columns = [column.app_id, column.pushkey, column.user_name]
  }
}
table "ratelimit_override" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "messages_per_second" {
    null = true
    type = bigint
  }
  column "burst_count" {
    null = true
    type = bigint
  }
  index "ratelimit_override_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "receipts_graph" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "receipt_type" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "event_ids" {
    null = false
    type = text
  }
  column "data" {
    null = false
    type = text
  }
  column "thread_id" {
    null = true
    type = text
  }
  index "receipts_graph_unique_index" {
    unique  = true
    columns = [column.room_id, column.receipt_type, column.user_id]
    where   = "(thread_id IS NULL)"
  }
  unique "receipts_graph_uniqueness_thread" {
    columns = [column.room_id, column.receipt_type, column.user_id, column.thread_id]
  }
}
table "receipts_linearized" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "receipt_type" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "data" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  column "event_stream_ordering" {
    null = true
    type = bigint
  }
  column "thread_id" {
    null = true
    type = text
  }
  index "receipts_linearized_event_id" {
    columns = [column.room_id, column.event_id]
  }
  index "receipts_linearized_id" {
    columns = [column.stream_id]
  }
  index "receipts_linearized_room_stream" {
    columns = [column.room_id, column.stream_id]
  }
  index "receipts_linearized_unique_index" {
    unique  = true
    columns = [column.room_id, column.receipt_type, column.user_id]
    where   = "(thread_id IS NULL)"
  }
  index "receipts_linearized_user" {
    columns = [column.user_id]
  }
  unique "receipts_linearized_uniqueness_thread" {
    columns = [column.room_id, column.receipt_type, column.user_id, column.thread_id]
  }
}
table "received_transactions" {
  schema = schema.public
  column "transaction_id" {
    null = true
    type = text
  }
  column "origin" {
    null = true
    type = text
  }
  column "ts" {
    null = true
    type = bigint
  }
  column "response_code" {
    null = true
    type = integer
  }
  column "response_json" {
    null = true
    type = bytea
  }
  column "has_been_referenced" {
    null    = true
    type    = smallint
    default = 0
  }
  index "received_transactions_ts" {
    columns = [column.ts]
  }
  unique "received_transactions_transaction_id_origin_key" {
    columns = [column.transaction_id, column.origin]
  }
}
table "redactions" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "redacts" {
    null = false
    type = text
  }
  column "have_censored" {
    null    = false
    type    = boolean
    default = false
  }
  column "received_ts" {
    null = true
    type = bigint
  }
  index "redactions_have_censored_ts" {
    columns = [column.received_ts]
    where   = "(NOT have_censored)"
  }
  index "redactions_redacts" {
    columns = [column.redacts]
  }
  unique "redactions_event_id_key" {
    columns = [column.event_id]
  }
}
table "refresh_tokens" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = text
  }
  column "token" {
    null = false
    type = text
  }
  column "next_token_id" {
    null = true
    type = bigint
  }
  column "expiry_ts" {
    null = true
    type = bigint
  }
  column "ultimate_session_expiry_ts" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "refresh_tokens_next_token_id_fkey" {
    columns     = [column.next_token_id]
    ref_columns = [table.refresh_tokens.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "refresh_tokens_next_token_id" {
    columns = [column.next_token_id]
    where   = "(next_token_id IS NOT NULL)"
  }
  unique "refresh_tokens_token_key" {
    columns = [column.token]
  }
}
table "registration_tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = text
  }
  column "uses_allowed" {
    null = true
    type = integer
  }
  column "pending" {
    null = false
    type = integer
  }
  column "completed" {
    null = false
    type = integer
  }
  column "expiry_time" {
    null = true
    type = bigint
  }
  unique "registration_tokens_token_key" {
    columns = [column.token]
  }
}
table "rejections" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "reason" {
    null = false
    type = text
  }
  column "last_check" {
    null = false
    type = text
  }
  unique "rejections_event_id_key" {
    columns = [column.event_id]
  }
}
table "remote_media_cache" {
  schema = schema.public
  column "media_origin" {
    null = true
    type = text
  }
  column "media_id" {
    null = true
    type = text
  }
  column "media_type" {
    null = true
    type = text
  }
  column "created_ts" {
    null = true
    type = bigint
  }
  column "upload_name" {
    null = true
    type = text
  }
  column "media_length" {
    null = true
    type = integer
  }
  column "filesystem_id" {
    null = true
    type = text
  }
  column "last_access_ts" {
    null = true
    type = bigint
  }
  column "quarantined_by" {
    null = true
    type = text
  }
  column "authenticated" {
    null    = false
    type    = boolean
    default = false
  }
  column "sha256" {
    null = true
    type = text
  }
  index "remote_media_cache_sha256" {
    columns = [column.sha256]
    where   = "(sha256 IS NOT NULL)"
  }
  unique "remote_media_cache_media_origin_media_id_key" {
    columns = [column.media_origin, column.media_id]
  }
}
table "remote_media_cache_thumbnails" {
  schema = schema.public
  column "media_origin" {
    null = true
    type = text
  }
  column "media_id" {
    null = true
    type = text
  }
  column "thumbnail_width" {
    null = true
    type = integer
  }
  column "thumbnail_height" {
    null = true
    type = integer
  }
  column "thumbnail_method" {
    null = true
    type = text
  }
  column "thumbnail_type" {
    null = true
    type = text
  }
  column "thumbnail_length" {
    null = true
    type = integer
  }
  column "filesystem_id" {
    null = true
    type = text
  }
  index "remote_media_repository_thumbn_media_origin_id_width_height_met" {
    unique  = true
    columns = [column.media_origin, column.media_id, column.thumbnail_width, column.thumbnail_height, column.thumbnail_type, column.thumbnail_method]
  }
}
table "room_account_data" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "account_data_type" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "content" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "room_account_data_room_id" {
    columns = [column.room_id]
  }
  index "room_account_data_stream_id" {
    columns = [column.user_id, column.stream_id]
  }
  unique "room_account_data_uniqueness" {
    columns = [column.user_id, column.room_id, column.account_data_type]
  }
}
table "room_alias_servers" {
  schema = schema.public
  column "room_alias" {
    null = false
    type = text
  }
  column "server" {
    null = false
    type = text
  }
  index "room_alias_servers_alias" {
    columns = [column.room_alias]
  }
}
table "room_aliases" {
  schema = schema.public
  column "room_alias" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "creator" {
    null = true
    type = text
  }
  index "room_aliases_id" {
    columns = [column.room_id]
  }
  unique "room_aliases_room_alias_key" {
    columns = [column.room_alias]
  }
}
table "room_ban_redactions" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "redacting_event_id" {
    null = false
    type = text
  }
  column "redact_end_ordering" {
    null = true
    type = bigint
  }
  unique "room_ban_redaction_uniqueness" {
    columns = [column.room_id, column.user_id]
  }
}
table "room_depth" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "min_depth" {
    null = true
    type = bigint
  }
  unique "room_depth_room_id_key" {
    columns = [column.room_id]
  }
}
table "room_forgetter_stream_pos" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  check "room_forgetter_stream_pos_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "room_forgetter_stream_pos_lock_key" {
    columns = [column.lock]
  }
}
table "room_memberships" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "sender" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "membership" {
    null = false
    type = text
  }
  column "forgotten" {
    null    = true
    type    = integer
    default = 0
  }
  column "display_name" {
    null = true
    type = text
  }
  column "avatar_url" {
    null = true
    type = text
  }
  column "event_stream_ordering" {
    null = true
    type = bigint
  }
  column "participant" {
    null    = true
    type    = boolean
    default = false
  }
  foreign_key "event_stream_ordering_fkey" {
    columns     = [column.event_stream_ordering]
    ref_columns = [table.events.column.stream_ordering]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "room_membership_user_room_idx" {
    columns = [column.user_id, column.room_id]
  }
  index "room_memberships_room_id" {
    columns = [column.room_id]
  }
  index "room_memberships_stream_ordering_idx" {
    columns = [column.event_stream_ordering]
  }
  index "room_memberships_user_id" {
    columns = [column.user_id]
  }
  index "room_memberships_user_room_forgotten" {
    columns = [column.user_id, column.room_id]
    where   = "(forgotten = 1)"
  }
  unique "room_memberships_event_id_key" {
    columns = [column.event_id]
  }
}
table "room_reports" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "received_ts" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "reason" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "room_retention" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "min_lifetime" {
    null = true
    type = bigint
  }
  column "max_lifetime" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.room_id, column.event_id]
  }
  index "room_retention_max_lifetime_idx" {
    columns = [column.max_lifetime]
  }
}
table "room_stats_current" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "current_state_events" {
    null = false
    type = integer
  }
  column "joined_members" {
    null = false
    type = integer
  }
  column "invited_members" {
    null = false
    type = integer
  }
  column "left_members" {
    null = false
    type = integer
  }
  column "banned_members" {
    null = false
    type = integer
  }
  column "local_users_in_room" {
    null = false
    type = integer
  }
  column "completed_delta_stream_id" {
    null = false
    type = bigint
  }
  column "knocked_members" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.room_id]
  }
}
table "room_stats_earliest_token" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "token" {
    null = false
    type = bigint
  }
  index "room_stats_earliest_token_idx" {
    unique  = true
    columns = [column.room_id]
  }
}
table "room_stats_state" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "name" {
    null = true
    type = text
  }
  column "canonical_alias" {
    null = true
    type = text
  }
  column "join_rules" {
    null = true
    type = text
  }
  column "history_visibility" {
    null = true
    type = text
  }
  column "encryption" {
    null = true
    type = text
  }
  column "avatar" {
    null = true
    type = text
  }
  column "guest_access" {
    null = true
    type = text
  }
  column "is_federatable" {
    null = true
    type = boolean
  }
  column "topic" {
    null = true
    type = text
  }
  column "room_type" {
    null = true
    type = text
  }
  index "room_stats_state_room" {
    unique  = true
    columns = [column.room_id]
  }
}
table "room_tags" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "tag" {
    null = false
    type = text
  }
  column "content" {
    null = false
    type = text
  }
  unique "room_tag_uniqueness" {
    columns = [column.user_id, column.room_id, column.tag]
  }
}
table "room_tags_revisions" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = true
    type = text
  }
  unique "room_tag_revisions_uniqueness" {
    columns = [column.user_id, column.room_id]
  }
}
table "rooms" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "is_public" {
    null = true
    type = boolean
  }
  column "creator" {
    null = true
    type = text
  }
  column "room_version" {
    null = true
    type = text
  }
  column "has_auth_chain_index" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.room_id]
  }
  index "public_room_index" {
    columns = [column.is_public]
  }
}
table "scheduled_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "action" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "resource_id" {
    null = true
    type = text
  }
  column "params" {
    null = true
    type = text
  }
  column "result" {
    null = true
    type = text
  }
  column "error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "scheduled_tasks_status" {
    columns = [column.status]
  }
  index "scheduled_tasks_timestamp" {
    columns = [column.timestamp]
  }
}
table "schema_compat_version" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "compat_version" {
    null = false
    type = integer
  }
  check "schema_compat_version_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "schema_compat_version_lock_key" {
    columns = [column.lock]
  }
}
table "schema_version" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "version" {
    null = false
    type = integer
  }
  column "upgraded" {
    null = false
    type = boolean
  }
  check "schema_version_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "schema_version_lock_key" {
    columns = [column.lock]
  }
}
table "server_keys_json" {
  schema = schema.public
  column "server_name" {
    null = false
    type = text
  }
  column "key_id" {
    null = false
    type = text
  }
  column "from_server" {
    null = false
    type = text
  }
  column "ts_added_ms" {
    null = false
    type = bigint
  }
  column "ts_valid_until_ms" {
    null = false
    type = bigint
  }
  column "key_json" {
    null = false
    type = bytea
  }
  unique "server_keys_json_uniqueness" {
    columns = [column.server_name, column.key_id, column.from_server]
  }
}
table "server_signature_keys" {
  schema = schema.public
  column "server_name" {
    null = true
    type = text
  }
  column "key_id" {
    null = true
    type = text
  }
  column "from_server" {
    null = true
    type = text
  }
  column "ts_added_ms" {
    null = true
    type = bigint
  }
  column "verify_key" {
    null = true
    type = bytea
  }
  column "ts_valid_until_ms" {
    null = true
    type = bigint
  }
  unique "server_signature_keys_server_name_key_id_key" {
    columns = [column.server_name, column.key_id]
  }
}
table "sessions" {
  schema = schema.public
  column "session_type" {
    null = false
    type = text
  }
  column "session_id" {
    null = false
    type = text
  }
  column "value" {
    null = false
    type = text
  }
  column "expiry_time_ms" {
    null = false
    type = bigint
  }
  unique "sessions_session_type_session_id_key" {
    columns = [column.session_type, column.session_id]
  }
}
table "sliding_sync_connection_lazy_members" {
  schema = schema.public
  column "connection_key" {
    null = false
    type = bigint
  }
  column "connection_position" {
    null = true
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "last_seen_ts" {
    null = false
    type = bigint
  }
  foreign_key "sliding_sync_connection_lazy_members_connection_key_fkey" {
    columns     = [column.connection_key]
    ref_columns = [table.sliding_sync_connections.column.connection_key]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "sliding_sync_connection_lazy_members_connection_position_fkey" {
    columns     = [column.connection_position]
    ref_columns = [table.sliding_sync_connection_positions.column.connection_position]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "sliding_sync_connection_lazy_members_idx" {
    unique  = true
    columns = [column.connection_key, column.room_id, column.user_id]
  }
  index "sliding_sync_connection_lazy_members_pos_idx" {
    columns = [column.connection_key, column.connection_position]
    where   = "(connection_position IS NOT NULL)"
  }
}
table "sliding_sync_connection_positions" {
  schema = schema.public
  column "connection_position" {
    null = false
    type = bigint
    identity {
      generated = ALWAYS
    }
  }
  column "connection_key" {
    null = false
    type = bigint
  }
  column "created_ts" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.connection_position]
  }
  foreign_key "sliding_sync_connection_positions_connection_key_fkey" {
    columns     = [column.connection_key]
    ref_columns = [table.sliding_sync_connections.column.connection_key]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "sliding_sync_connection_positions_key" {
    columns = [column.connection_key]
  }
  index "sliding_sync_connection_positions_ts_idx" {
    columns = [column.created_ts]
  }
}
table "sliding_sync_connection_required_state" {
  schema = schema.public
  column "required_state_id" {
    null = false
    type = bigint
    identity {
      generated = ALWAYS
    }
  }
  column "connection_key" {
    null = false
    type = bigint
  }
  column "required_state" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.required_state_id]
  }
  foreign_key "sliding_sync_connection_required_state_connection_key_fkey" {
    columns     = [column.connection_key]
    ref_columns = [table.sliding_sync_connections.column.connection_key]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "sliding_sync_connection_required_state_conn_pos" {
    columns = [column.connection_key]
  }
}
table "sliding_sync_connection_room_configs" {
  schema = schema.public
  column "connection_position" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "timeline_limit" {
    null = false
    type = bigint
  }
  column "required_state_id" {
    null = false
    type = bigint
  }
  foreign_key "sliding_sync_connection_room_configs_connection_position_fkey" {
    columns     = [column.connection_position]
    ref_columns = [table.sliding_sync_connection_positions.column.connection_position]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "sliding_sync_connection_room_configs_required_state_id_fkey" {
    columns     = [column.required_state_id]
    ref_columns = [table.sliding_sync_connection_required_state.column.required_state_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "sliding_sync_connection_room_configs_idx" {
    unique  = true
    columns = [column.connection_position, column.room_id]
  }
  index "sliding_sync_connection_room_configs_required_state_id_idx" {
    columns = [column.required_state_id]
  }
}
table "sliding_sync_connection_streams" {
  schema = schema.public
  column "connection_position" {
    null = false
    type = bigint
  }
  column "stream" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "room_status" {
    null = false
    type = text
  }
  column "last_token" {
    null = true
    type = text
  }
  foreign_key "sliding_sync_connection_streams_connection_position_fkey" {
    columns     = [column.connection_position]
    ref_columns = [table.sliding_sync_connection_positions.column.connection_position]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "sliding_sync_connection_streams_idx" {
    unique  = true
    columns = [column.connection_position, column.room_id, column.stream]
  }
}
table "sliding_sync_connections" {
  schema = schema.public
  column "connection_key" {
    null = false
    type = bigint
    identity {
      generated = ALWAYS
    }
  }
  column "user_id" {
    null = false
    type = text
  }
  column "effective_device_id" {
    null = false
    type = text
  }
  column "conn_id" {
    null = false
    type = text
  }
  column "created_ts" {
    null = false
    type = bigint
  }
  column "last_used_ts" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.connection_key]
  }
  index "sliding_sync_connections_idx" {
    columns = [column.user_id, column.effective_device_id, column.conn_id]
  }
  index "sliding_sync_connections_ts_idx" {
    columns = [column.created_ts]
  }
}
table "sliding_sync_joined_rooms" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "event_stream_ordering" {
    null = false
    type = bigint
  }
  column "bump_stamp" {
    null = true
    type = bigint
  }
  column "room_type" {
    null = true
    type = text
  }
  column "room_name" {
    null = true
    type = text
  }
  column "is_encrypted" {
    null    = false
    type    = boolean
    default = false
  }
  column "tombstone_successor_room_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.room_id]
  }
  foreign_key "sliding_sync_joined_rooms_event_stream_ordering_fkey" {
    columns     = [column.event_stream_ordering]
    ref_columns = [table.events.column.stream_ordering]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sliding_sync_joined_rooms_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "sliding_sync_joined_rooms_event_stream_ordering" {
    unique  = true
    columns = [column.event_stream_ordering]
  }
}
table "sliding_sync_joined_rooms_to_recalculate" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.room_id]
  }
  foreign_key "sliding_sync_joined_rooms_to_recalculate_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "sliding_sync_membership_snapshots" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "sender" {
    null = false
    type = text
  }
  column "membership_event_id" {
    null = false
    type = text
  }
  column "membership" {
    null = false
    type = text
  }
  column "forgotten" {
    null    = false
    type    = integer
    default = 0
  }
  column "event_stream_ordering" {
    null = false
    type = bigint
  }
  column "event_instance_name" {
    null = false
    type = text
  }
  column "has_known_state" {
    null    = false
    type    = boolean
    default = false
  }
  column "room_type" {
    null = true
    type = text
  }
  column "room_name" {
    null = true
    type = text
  }
  column "is_encrypted" {
    null    = false
    type    = boolean
    default = false
  }
  column "tombstone_successor_room_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.room_id, column.user_id]
  }
  foreign_key "sliding_sync_membership_snapshots_event_stream_ordering_fkey" {
    columns     = [column.event_stream_ordering]
    ref_columns = [table.events.column.stream_ordering]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sliding_sync_membership_snapshots_membership_event_id_fkey" {
    columns     = [column.membership_event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sliding_sync_membership_snapshots_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "sliding_sync_membership_snapshots_event_stream_ordering" {
    unique  = true
    columns = [column.event_stream_ordering]
  }
  index "sliding_sync_membership_snapshots_membership_event_id_idx" {
    columns = [column.membership_event_id]
  }
  index "sliding_sync_membership_snapshots_user_id_stream_ordering" {
    columns = [column.user_id, column.event_stream_ordering]
  }
}
table "state_events" {
  schema = schema.public
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "state_key" {
    null = false
    type = text
  }
  column "prev_state" {
    null = true
    type = text
  }
  unique "state_events_event_id_key" {
    columns = [column.event_id]
  }
}
table "state_group_edges" {
  schema = schema.public
  column "state_group" {
    null = false
    type = bigint
  }
  column "prev_state_group" {
    null = false
    type = bigint
  }
  index "state_group_edges_prev_idx" {
    columns = [column.prev_state_group]
  }
  index "state_group_edges_unique_idx" {
    unique  = true
    columns = [column.state_group, column.prev_state_group]
  }
}
table "state_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "state_groups_room_id_idx" {
    columns = [column.room_id]
  }
}
table "state_groups_pending_deletion" {
  schema = schema.public
  column "sequence_number" {
    null = false
    type = bigint
    identity {
      generated = ALWAYS
    }
  }
  column "state_group" {
    null = false
    type = bigint
  }
  column "insertion_ts" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.sequence_number]
  }
  index "state_groups_pending_deletion_insertion_ts" {
    columns = [column.insertion_ts]
  }
  index "state_groups_pending_deletion_state_group" {
    unique  = true
    columns = [column.state_group]
  }
}
table "state_groups_persisting" {
  schema = schema.public
  column "state_group" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.state_group, column.instance_name]
  }
  index "state_groups_persisting_instance_name" {
    columns = [column.instance_name]
  }
}
table "state_groups_state" {
  schema = schema.public
  column "state_group" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "state_key" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  index "state_groups_state_type_idx" {
    columns = [column.state_group, column.type, column.state_key]
  }
}
table "stats_incremental_position" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  check "stats_incremental_position_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "stats_incremental_position_lock_key" {
    columns = [column.lock]
  }
}
table "sticky_events" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = integer
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_stream_ordering" {
    null = false
    type = integer
  }
  column "sender" {
    null = false
    type = text
  }
  column "expires_at" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.stream_id]
  }
  index "sticky_events_room_idx" {
    columns = [column.room_id, column.event_stream_ordering]
  }
  unique "sticky_events_event_stream_ordering_key" {
    columns = [column.event_stream_ordering]
  }
}
table "stream_ordering_to_exterm" {
  schema = schema.public
  column "stream_ordering" {
    null = false
    type = bigint
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  index "stream_ordering_to_exterm_idx" {
    columns = [column.stream_ordering]
  }
  index "stream_ordering_to_exterm_rm_idx" {
    columns = [column.room_id, column.stream_ordering]
  }
}
table "stream_positions" {
  schema = schema.public
  column "stream_name" {
    null = false
    type = text
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "stream_id" {
    null = false
    type = bigint
  }
  index "stream_positions_idx" {
    unique  = true
    columns = [column.stream_name, column.instance_name]
  }
}
table "thread_subscriptions" {
  schema  = schema.public
  comment = "Tracks local users that subscribe to threads"
  column "stream_id" {
    null = false
    type = integer
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "subscribed" {
    null    = false
    type    = boolean
    comment = "Whether the user is subscribed to the thread or not. We track unsubscribed threads because we need to stream the subscription change to the client."
  }
  column "automatic" {
    null    = false
    type    = boolean
    comment = "True if the user was subscribed to the thread automatically by their client, or false if the client manually requested the subscription."
  }
  column "unsubscribed_at_stream_ordering" {
    null    = true
    type    = bigint
    comment = "The maximum stream_ordering in the room when the unsubscription was made."
  }
  column "unsubscribed_at_topological_ordering" {
    null    = true
    type    = bigint
    comment = "The maximum topological_ordering in the room when the unsubscription was made."
  }
  primary_key {
    columns = [column.stream_id]
  }
  foreign_key "thread_subscriptions_fk_events" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "thread_subscriptions_fk_rooms" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "thread_subscriptions_fk_users" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.name]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "thread_subscriptions_by_event" {
    columns = [column.event_id]
  }
  index "thread_subscriptions_by_user" {
    columns = [column.user_id, column.stream_id]
  }
  index "thread_subscriptions_user_room" {
    columns = [column.user_id, column.room_id]
  }
  unique "thread_subscriptions_room_id_event_id_user_id_key" {
    columns = [column.room_id, column.event_id, column.user_id]
  }
}
table "threads" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "thread_id" {
    null = false
    type = text
  }
  column "latest_event_id" {
    null    = false
    type    = text
    comment = "the ID of the event that is latest, ordered by (topological_ordering, stream_ordering)"
  }
  column "topological_ordering" {
    null    = false
    type    = bigint
    comment = "the topological ordering of the thread''s LATEST event.\nUsed as the primary way of ordering threads by recency in a room."
  }
  column "stream_ordering" {
    null    = false
    type    = bigint
    comment = "the stream ordering of the thread's LATEST event.\nUsed as a tie-breaker for ordering threads by recency in a room, when the topological order is a tie.\nAlso used for recency ordering in sliding sync."
  }
  index "threads_ordering_idx" {
    columns = [column.room_id, column.topological_ordering, column.stream_ordering]
  }
  unique "threads_uniqueness" {
    columns = [column.room_id, column.thread_id]
  }
}
table "threepid_guest_access_tokens" {
  schema = schema.public
  column "medium" {
    null = true
    type = text
  }
  column "address" {
    null = true
    type = text
  }
  column "guest_access_token" {
    null = true
    type = text
  }
  column "first_inviter" {
    null = true
    type = text
  }
  index "threepid_guest_access_tokens_index" {
    unique  = true
    columns = [column.medium, column.address]
  }
}
table "threepid_validation_session" {
  schema = schema.public
  column "session_id" {
    null = false
    type = text
  }
  column "medium" {
    null = false
    type = text
  }
  column "address" {
    null = false
    type = text
  }
  column "client_secret" {
    null = false
    type = text
  }
  column "last_send_attempt" {
    null = false
    type = bigint
  }
  column "validated_at" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.session_id]
  }
}
table "threepid_validation_token" {
  schema = schema.public
  column "token" {
    null = false
    type = text
  }
  column "session_id" {
    null = false
    type = text
  }
  column "next_link" {
    null = true
    type = text
  }
  column "expires" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.token]
  }
  index "threepid_validation_token_session_id" {
    columns = [column.session_id]
  }
}
table "timeline_gaps" {
  schema = schema.public
  column "room_id" {
    null = false
    type = text
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "stream_ordering" {
    null = false
    type = bigint
  }
  index "timeline_gaps_room_id" {
    columns = [column.room_id, column.stream_ordering]
  }
}
table "ui_auth_sessions" {
  schema = schema.public
  column "session_id" {
    null = false
    type = text
  }
  column "creation_time" {
    null = false
    type = bigint
  }
  column "serverdict" {
    null = false
    type = text
  }
  column "clientdict" {
    null = false
    type = text
  }
  column "uri" {
    null = false
    type = text
  }
  column "method" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  unique "ui_auth_sessions_session_id_key" {
    columns = [column.session_id]
  }
}
table "ui_auth_sessions_credentials" {
  schema = schema.public
  column "session_id" {
    null = false
    type = text
  }
  column "stage_type" {
    null = false
    type = text
  }
  column "result" {
    null = false
    type = text
  }
  foreign_key "ui_auth_sessions_credentials_session_id_fkey" {
    columns     = [column.session_id]
    ref_columns = [table.ui_auth_sessions.column.session_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "ui_auth_sessions_credentials_session_id_stage_type_key" {
    columns = [column.session_id, column.stage_type]
  }
}
table "ui_auth_sessions_ips" {
  schema = schema.public
  column "session_id" {
    null = false
    type = text
  }
  column "ip" {
    null = false
    type = text
  }
  column "user_agent" {
    null = false
    type = text
  }
  foreign_key "ui_auth_sessions_ips_session_id_fkey" {
    columns     = [column.session_id]
    ref_columns = [table.ui_auth_sessions.column.session_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "ui_auth_sessions_ips_session_id_ip_user_agent_key" {
    columns = [column.session_id, column.ip, column.user_agent]
  }
}
table "un_partial_stated_event_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "event_id" {
    null = false
    type = text
  }
  column "rejection_status_changed" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.stream_id]
  }
  foreign_key "un_partial_stated_event_stream_event_id_fkey" {
    columns     = [column.event_id]
    ref_columns = [table.events.column.event_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "un_partial_stated_event_stream_room_id" {
    unique  = true
    columns = [column.event_id]
  }
}
table "un_partial_stated_room_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.stream_id]
  }
  foreign_key "un_partial_stated_room_stream_room_id_fkey" {
    columns     = [column.room_id]
    ref_columns = [table.rooms.column.room_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "un_partial_stated_room_stream_room_id" {
    columns = [column.room_id]
  }
}
table "user_daily_visits" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "device_id" {
    null = true
    type = text
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "user_agent" {
    null = true
    type = text
  }
  index "user_daily_visits_ts_idx" {
    columns = [column.timestamp]
  }
  index "user_daily_visits_uts_idx" {
    columns = [column.user_id, column.timestamp]
  }
}
table "user_directory" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = true
    type = text
  }
  column "display_name" {
    null = true
    type = text
  }
  column "avatar_url" {
    null = true
    type = text
  }
  index "user_directory_room_idx" {
    columns = [column.room_id]
  }
  index "user_directory_user_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "user_directory_search" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "vector" {
    null = true
    type = tsvector
  }
  index "user_directory_search_fts_idx" {
    columns = [column.vector]
    type    = GIN
  }
  index "user_directory_search_user_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "user_directory_stale_remote_users" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "user_server_name" {
    null = false
    type = text
  }
  column "next_try_at_ts" {
    null = false
    type = bigint
  }
  column "retry_counter" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.user_id]
  }
  index "user_directory_stale_remote_users_next_try_by_server_idx" {
    columns = [column.user_server_name, column.next_try_at_ts]
  }
  index "user_directory_stale_remote_users_next_try_idx" {
    columns = [column.next_try_at_ts, column.user_server_name]
  }
}
table "user_directory_stream_pos" {
  schema = schema.public
  column "lock" {
    null    = false
    type    = character(1)
    default = "X"
  }
  column "stream_id" {
    null = true
    type = bigint
  }
  check "user_directory_stream_pos_lock_check" {
    expr = "(lock = 'X'::bpchar)"
  }
  unique "user_directory_stream_pos_lock_key" {
    columns = [column.lock]
  }
}
table "user_external_ids" {
  schema = schema.public
  column "auth_provider" {
    null = false
    type = text
  }
  column "external_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  index "user_external_ids_user_id_idx" {
    columns = [column.user_id]
  }
  unique "user_external_ids_auth_provider_external_id_key" {
    columns = [column.auth_provider, column.external_id]
  }
}
table "user_filters" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "filter_id" {
    null = false
    type = bigint
  }
  column "filter_json" {
    null = false
    type = bytea
  }
  column "full_user_id" {
    null = true
    type = text
  }
  index "full_users_unique_idx" {
    unique  = true
    columns = [column.full_user_id, column.filter_id]
  }
  index "user_filters_unique" {
    unique  = true
    columns = [column.user_id, column.filter_id]
  }
  check "full_user_id_not_null" {
    expr = "(full_user_id IS NOT NULL)"
  }
}
table "user_ips" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "access_token" {
    null = false
    type = text
  }
  column "device_id" {
    null = true
    type = text
  }
  column "ip" {
    null = false
    type = text
  }
  column "user_agent" {
    null = false
    type = text
  }
  column "last_seen" {
    null = false
    type = bigint
  }
  index "user_ips_device_id" {
    columns = [column.user_id, column.device_id, column.last_seen]
  }
  index "user_ips_last_seen" {
    columns = [column.user_id, column.last_seen]
  }
  index "user_ips_last_seen_only" {
    columns = [column.last_seen]
  }
  index "user_ips_user_token_ip_unique_index" {
    unique  = true
    columns = [column.user_id, column.access_token, column.ip]
  }
}
table "user_reports" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "received_ts" {
    null = false
    type = bigint
  }
  column "target_user_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "reason" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "user_reports_target_user_id" {
    columns = [column.target_user_id]
  }
  index "user_reports_user_id" {
    columns = [column.user_id]
  }
}
table "user_signature_stream" {
  schema = schema.public
  column "stream_id" {
    null = false
    type = bigint
  }
  column "from_user_id" {
    null = false
    type = text
  }
  column "user_ids" {
    null = false
    type = text
  }
  column "instance_name" {
    null = true
    type = text
  }
  index "user_signature_stream_idx" {
    unique  = true
    columns = [column.stream_id]
  }
}
table "user_stats_current" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "joined_rooms" {
    null = false
    type = bigint
  }
  column "completed_delta_stream_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.user_id]
  }
}
table "user_threepid_id_server" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "medium" {
    null = false
    type = text
  }
  column "address" {
    null = false
    type = text
  }
  column "id_server" {
    null = false
    type = text
  }
  index "user_threepid_id_server_idx" {
    unique  = true
    columns = [column.user_id, column.medium, column.address, column.id_server]
  }
}
table "user_threepids" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "medium" {
    null = false
    type = text
  }
  column "address" {
    null = false
    type = text
  }
  column "validated_at" {
    null = false
    type = bigint
  }
  column "added_at" {
    null = false
    type = bigint
  }
  index "user_threepids_medium_address" {
    columns = [column.medium, column.address]
  }
  index "user_threepids_user_id" {
    columns = [column.user_id]
  }
  unique "medium_address" {
    columns = [column.medium, column.address]
  }
}
table "users" {
  schema = schema.public
  column "name" {
    null = true
    type = text
  }
  column "password_hash" {
    null = true
    type = text
  }
  column "creation_ts" {
    null = true
    type = bigint
  }
  column "admin" {
    null    = false
    type    = smallint
    default = 0
  }
  column "upgrade_ts" {
    null = true
    type = bigint
  }
  column "is_guest" {
    null    = false
    type    = smallint
    default = 0
  }
  column "appservice_id" {
    null = true
    type = text
  }
  column "consent_version" {
    null = true
    type = text
  }
  column "consent_server_notice_sent" {
    null = true
    type = text
  }
  column "user_type" {
    null = true
    type = text
  }
  column "deactivated" {
    null    = false
    type    = smallint
    default = 0
  }
  column "shadow_banned" {
    null = true
    type = boolean
  }
  column "consent_ts" {
    null = true
    type = bigint
  }
  column "approved" {
    null = true
    type = boolean
  }
  column "locked" {
    null    = false
    type    = boolean
    default = false
  }
  column "suspended" {
    null    = false
    type    = boolean
    default = false
  }
  index "users_creation_ts" {
    columns = [column.creation_ts]
  }
  unique "users_name_key" {
    columns = [column.name]
  }
}
table "users_in_public_rooms" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  index "users_in_public_rooms_r_idx" {
    columns = [column.room_id]
  }
  index "users_in_public_rooms_u_idx" {
    unique  = true
    columns = [column.user_id, column.room_id]
  }
}
table "users_pending_deactivation" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
}
table "users_to_send_full_presence_to" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "presence_stream_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.user_id]
  }
  foreign_key "users_to_send_full_presence_to_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.name]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "users_who_share_private_rooms" {
  schema = schema.public
  column "user_id" {
    null = false
    type = text
  }
  column "other_user_id" {
    null = false
    type = text
  }
  column "room_id" {
    null = false
    type = text
  }
  index "users_who_share_private_rooms_o_idx" {
    columns = [column.other_user_id]
  }
  index "users_who_share_private_rooms_r_idx" {
    columns = [column.room_id]
  }
  index "users_who_share_private_rooms_u_idx" {
    unique  = true
    columns = [column.user_id, column.other_user_id, column.room_id]
  }
}
table "worker_locks" {
  schema = schema.public
  column "lock_name" {
    null = false
    type = text
  }
  column "lock_key" {
    null = false
    type = text
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "token" {
    null = false
    type = text
  }
  column "last_renewed_ts" {
    null = false
    type = bigint
  }
  index "worker_locks_key" {
    unique  = true
    columns = [column.lock_name, column.lock_key]
  }
}
table "worker_read_write_locks" {
  schema = schema.public
  column "lock_name" {
    null = false
    type = text
  }
  column "lock_key" {
    null = false
    type = text
  }
  column "instance_name" {
    null = false
    type = text
  }
  column "write_lock" {
    null = false
    type = boolean
  }
  column "token" {
    null = false
    type = text
  }
  column "last_renewed_ts" {
    null = false
    type = bigint
  }
  foreign_key "worker_read_write_locks_lock_name_lock_key_write_lock_fkey" {
    columns     = [column.lock_name, column.lock_key, column.write_lock]
    ref_columns = [table.worker_read_write_locks_mode.column.lock_name, table.worker_read_write_locks_mode.column.lock_key, table.worker_read_write_locks_mode.column.write_lock]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "worker_read_write_locks_key" {
    unique  = true
    columns = [column.lock_name, column.lock_key, column.token]
  }
  index "worker_read_write_locks_write" {
    unique  = true
    columns = [column.lock_name, column.lock_key]
    where   = "write_lock"
  }
}
table "worker_read_write_locks_mode" {
  schema = schema.public
  column "lock_name" {
    null = false
    type = text
  }
  column "lock_key" {
    null = false
    type = text
  }
  column "write_lock" {
    null = false
    type = boolean
  }
  column "token" {
    null = false
    type = text
  }
  foreign_key "worker_read_write_locks_mode_foreign" {
    columns     = [column.lock_name, column.lock_key, column.token]
    ref_columns = [table.worker_read_write_locks.column.lock_name, table.worker_read_write_locks.column.lock_key, table.worker_read_write_locks.column.token]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "worker_read_write_locks_mode_key" {
    unique  = true
    columns = [column.lock_name, column.lock_key]
  }
  index "worker_read_write_locks_mode_type" {
    unique  = true
    columns = [column.lock_name, column.lock_key, column.write_lock]
  }
}
schema "public" {
  comment = "standard public schema"
}
