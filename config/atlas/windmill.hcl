Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "edges" {
  schema = schema.graph
  column "id" {
    null = false
    type = bigserial
  }
  column "from_node" {
    null = false
    type = text
  }
  column "to_node" {
    null = false
    type = text
  }
  column "edge_kind" {
    null = false
    type = text
  }
  column "metadata" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "edges_from_node_fkey" {
    columns     = [column.from_node]
    ref_columns = [table.nodes.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "edges_to_node_fkey" {
    columns     = [column.to_node]
    ref_columns = [table.nodes.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "graph_edges_from_idx" {
    columns = [column.from_node]
  }
  index "graph_edges_to_idx" {
    columns = [column.to_node]
  }
  unique "graph_edges_unique" {
    columns = [column.from_node, column.to_node, column.edge_kind]
  }
}
table "nodes" {
  schema = schema.graph
  column "id" {
    null = false
    type = text
  }
  column "kind" {
    null = false
    type = text
  }
  column "label" {
    null = false
    type = text
  }
  column "tier" {
    null = true
    type = integer
  }
  column "metadata" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
}
table "entries" {
  schema = schema.memory
  column "memory_id" {
    null = false
    type = text
  }
  column "scope_kind" {
    null = false
    type = text
  }
  column "scope_id" {
    null = false
    type = text
  }
  column "object_type" {
    null = false
    type = text
  }
  column "title" {
    null = false
    type = text
  }
  column "content" {
    null = false
    type = text
  }
  column "provenance" {
    null = false
    type = text
  }
  column "retention_class" {
    null = false
    type = text
  }
  column "consent_boundary" {
    null = false
    type = text
  }
  column "delegation_boundary" {
    null = true
    type = text
  }
  column "source_uri" {
    null = true
    type = text
  }
  column "metadata" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "last_refreshed_at" {
    null = false
    type = timestamptz
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "expires_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.memory_id]
  }
  index "memory_entries_expiry_idx" {
    columns = [column.expires_at]
  }
  index "memory_entries_metadata_gin_idx" {
    columns = [column.metadata]
    type    = GIN
  }
  index "memory_entries_object_type_idx" {
    columns = [column.object_type]
  }
  index "memory_entries_refresh_idx" {
    on {
      desc   = true
      column = column.last_refreshed_at
    }
  }
  index "memory_entries_scope_idx" {
    columns = [column.scope_kind, column.scope_id]
  }
  check "memory_entries_scope_kind_ck" {
    expr = "(scope_kind = ANY (ARRAY['owner'::text, 'workspace'::text]))"
  }
}
table "idempotency_records" {
  schema = schema.platform
  column "idempotency_key" {
    null = false
    type = text
  }
  column "workflow_id" {
    null = false
    type = text
  }
  column "actor_id" {
    null = false
    type = text
  }
  column "actor_intent_id" {
    null = true
    type = text
  }
  column "target_service_id" {
    null    = false
    type    = text
    default = ""
  }
  column "submitted_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "completed_at" {
    null = true
    type = timestamptz
  }
  column "status" {
    null    = false
    type    = text
    default = "in_flight"
  }
  column "windmill_job_id" {
    null = true
    type = text
  }
  column "result" {
    null = true
    type = jsonb
  }
  column "metadata" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "expires_at" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.idempotency_key]
  }
  index "platform_idempotency_records_expiry_idx" {
    columns = [column.expires_at]
  }
  index "platform_idempotency_records_in_flight_idx" {
    columns = [column.workflow_id, column.target_service_id]
    where   = "(status = 'in_flight'::text)"
  }
  index "platform_idempotency_records_intent_idx" {
    columns = [column.actor_intent_id]
  }
  check "platform_idempotency_status_ck" {
    expr = "(status = ANY (ARRAY['in_flight'::text, 'completed'::text, 'failed'::text, 'aborted'::text, 'budget_exceeded'::text, 'rolled_back'::text]))"
  }
}
table "_sqlx_migrations" {
  schema = schema.public
  column "version" {
    null = false
    type = bigint
  }
  column "description" {
    null = false
    type = text
  }
  column "installed_on" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "success" {
    null = false
    type = boolean
  }
  column "checksum" {
    null = false
    type = bytea
  }
  column "execution_time" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.version]
  }
}
table "account" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "id" {
    null = false
    type = serial
  }
  column "expires_at" {
    null = false
    type = timestamptz
  }
  column "refresh_token" {
    null = false
    type = character_varying(10000)
  }
  column "client" {
    null = false
    type = character_varying(50)
  }
  column "refresh_error" {
    null = true
    type = text
  }
  column "grant_type" {
    null    = false
    type    = character_varying(50)
    default = "authorization_code"
  }
  column "cc_client_id" {
    null = true
    type = character_varying(500)
  }
  column "cc_client_secret" {
    null = true
    type = character_varying(500)
  }
  column "cc_token_url" {
    null = true
    type = character_varying(500)
  }
  column "mcp_server_url" {
    null = true
    type = text
  }
  column "is_workspace_integration" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.workspace_id, column.id]
  }
  foreign_key "account_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_account_mcp_server_url" {
    columns = [column.mcp_server_url]
    where   = "(mcp_server_url IS NOT NULL)"
  }
}
table "agent_token_blacklist" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying
  }
  column "expires_at" {
    null = false
    type = timestamp
  }
  column "blacklisted_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  column "blacklisted_by" {
    null = false
    type = character_varying
  }
  primary_key {
    columns = [column.token]
  }
  index "idx_agent_token_blacklist_expires_at" {
    columns = [column.expires_at]
  }
}
table "ai_agent_memory" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "step_id" {
    null = false
    type = character_varying(255)
  }
  column "messages" {
    null = false
    type = jsonb
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.workspace_id, column.conversation_id, column.step_id]
  }
}
table "ai_chat_usage" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "session_id" {
    null = false
    type = character_varying(36)
  }
  column "provider" {
    null = false
    type = character_varying(50)
  }
  column "model" {
    null = false
    type = character_varying(255)
  }
  column "mode" {
    null = false
    type = character_varying(50)
  }
  column "message_count" {
    null    = false
    type    = integer
    default = 1
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_ai_chat_usage_created_at" {
    columns = [column.created_at]
  }
  unique "ai_chat_usage_session_id_key" {
    columns = [column.session_id]
  }
}
table "alerts" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "alert_type" {
    null = false
    type = character_varying(50)
  }
  column "message" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  column "acknowledged" {
    null = true
    type = boolean
  }
  column "workspace_id" {
    null = true
    type = text
  }
  column "acknowledged_workspace" {
    null = true
    type = boolean
  }
  column "resource" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "alerts_by_workspace" {
    columns = [column.workspace_id]
  }
}
table "app" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "summary" {
    null    = false
    type    = character_varying(1000)
    default = ""
  }
  column "policy" {
    null = false
    type = jsonb
  }
  column "versions" {
    null = false
    type = sql("bigint[]")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "draft_only" {
    null = true
    type = boolean
  }
  column "custom_path" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "app_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "app_custom_path_check" {
    expr = "(custom_path ~ '^[\\w-]+(\\/[\\w-]+)*$'::text)"
  }
  unique "unique_path_workspace_id" {
    columns = [column.workspace_id, column.path]
  }
}
table "app_bundles" {
  schema = schema.public
  column "app_version_id" {
    null = false
    type = bigint
  }
  column "w_id" {
    null = false
    type = character_varying(255)
  }
  column "file_type" {
    null = false
    type = character_varying(10)
  }
  column "data" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.app_version_id, column.file_type]
  }
}
table "app_script" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "app" {
    null = false
    type = bigserial
  }
  column "hash" {
    null = false
    type = character(64)
  }
  column "lock" {
    null = true
    type = text
  }
  column "code" {
    null = false
    type = text
  }
  column "code_sha256" {
    null = false
    type = character(64)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "app_script_app_fkey" {
    columns     = [column.app]
    ref_columns = [table.app.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "app_script_hash_key" {
    columns = [column.hash]
  }
}
table "app_version" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "app_id" {
    null = false
    type = bigint
  }
  column "value" {
    null = false
    type = json
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "raw_app" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "app_version_flow_id_fkey" {
    columns     = [column.app_id]
    ref_columns = [table.app.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "app_version_lite" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "value" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "app_version_lite_id_fkey" {
    columns     = [column.id]
    ref_columns = [table.app_version.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "asset" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "kind" {
    null = false
    type = enum.asset_kind
  }
  column "usage_access_type" {
    null = true
    type = enum.asset_access_type
  }
  column "usage_path" {
    null = false
    type = character_varying(255)
  }
  column "usage_kind" {
    null = false
    type = enum.asset_usage_kind
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "id" {
    null = false
    type = bigserial
  }
  column "columns" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.workspace_id, column.path, column.kind, column.usage_path, column.usage_kind]
  }
  foreign_key "asset_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "idx_asset_job_pruning" {
    where = "(usage_kind = 'job'::public.asset_usage_kind)"
    on {
      column = column.workspace_id
    }
    on {
      column = column.path
    }
    on {
      column = column.kind
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "idx_asset_usage" {
    columns = [column.workspace_id, column.usage_path, column.usage_kind]
  }
  index "idx_asset_ws_path_kind_recent" {
    include = [column.usage_kind, column.usage_path]
    on {
      column = column.workspace_id
    }
    on {
      column = column.path
    }
    on {
      column = column.kind
    }
    on {
      desc   = true
      column = column.created_at
    }
    on {
      desc   = true
      column = column.id
    }
  }
  unique "asset_id_key" {
    columns = [column.id]
  }
}
table "audit" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "id" {
    null = false
    type = bigserial
  }
  column "timestamp" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "username" {
    null = false
    type = character_varying(255)
  }
  column "operation" {
    null = false
    type = character_varying(50)
  }
  column "action_kind" {
    null = false
    type = enum.action_kind
  }
  column "resource" {
    null = true
    type = character_varying(255)
  }
  column "parameters" {
    null = true
    type = jsonb
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "span" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.workspace_id, column.id]
  }
  index "idx_audit_recent_login_activities" {
    columns = [column.timestamp, column.username]
    where   = "((operation)::text = ANY ((ARRAY['users.login'::character varying, 'oauth.login'::character varying, 'users.token.refresh'::character varying])::text[]))"
  }
  index "ix_audit_timestamps" {
    on {
      desc   = true
      column = column.timestamp
    }
  }
}
table "audit_partitioned" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "id" {
    null = false
    type = bigserial
  }
  column "timestamp" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "username" {
    null = false
    type = character_varying(255)
  }
  column "operation" {
    null = false
    type = character_varying(50)
  }
  column "action_kind" {
    null = false
    type = enum.action_kind
  }
  column "resource" {
    null = true
    type = character_varying(255)
  }
  column "parameters" {
    null = true
    type = jsonb
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "span" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id, column.timestamp]
  }
  index "idx_audit_partitioned_recent_login_activities" {
    columns = [column.timestamp, column.username]
    where   = "((operation)::text = ANY ((ARRAY['users.login'::character varying, 'oauth.login'::character varying, 'users.token.refresh'::character varying])::text[]))"
  }
  index "idx_audit_partitioned_workspace" {
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.timestamp
    }
  }
  index "ix_audit_partitioned_timestamps" {
    on {
      desc   = true
      column = column.timestamp
    }
  }
  partition {
    type    = RANGE
    columns = [column.timestamp]
  }
}
table "autoscaling_event" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "worker_group" {
    null = false
    type = text
  }
  column "event_type" {
    null = false
    type = enum.autoscaling_event_type
  }
  column "desired_workers" {
    null = false
    type = integer
  }
  column "applied_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "reason" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "autoscaling_event_worker_group_idx" {
    columns = [column.worker_group, column.applied_at]
  }
}
table "capture" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "main_args" {
    null    = false
    type    = jsonb
    default = "null"
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "trigger_kind" {
    null = false
    type = enum.trigger_kind
  }
  column "preprocessor_args" {
    null = true
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "capture_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "capture_payload_too_big" {
    expr = "(length((main_args)::text) < (512 * 1024))"
  }
}
table "capture_config" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "trigger_kind" {
    null = false
    type = enum.trigger_kind
  }
  column "trigger_config" {
    null = true
    type = jsonb
  }
  column "owner" {
    null = false
    type = character_varying(50)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_client_ping" {
    null = true
    type = timestamptz
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.workspace_id, column.path, column.is_flow, column.trigger_kind]
  }
  foreign_key "capture_config_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "cloud_workspace_settings" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "threshold_alert_amount" {
    null = true
    type = integer
  }
  column "last_alert_sent" {
    null = true
    type = timestamp
  }
  column "last_warning_sent" {
    null = true
    type = timestamp
  }
  column "is_past_due" {
    null    = false
    type    = boolean
    default = false
  }
  column "max_tolerated_executions" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.workspace_id]
  }
  foreign_key "cloud_workspace_settings_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "concurrency_counter" {
  schema = schema.public
  column "concurrency_id" {
    null = false
    type = character_varying(1000)
  }
  column "job_uuids" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.concurrency_id]
  }
}
table "concurrency_key" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "ended_at" {
    null = true
    type = timestamptz
  }
  column "job_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.job_id]
  }
  index "concurrency_key_ended_at_idx" {
    on {
      column = column.key
    }
    on {
      desc   = true
      column = column.ended_at
    }
  }
}
table "concurrency_locks" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying
  }
  column "last_locked_at" {
    null = false
    type = timestamp
  }
  column "owner" {
    null = true
    type = character_varying
  }
  primary_key {
    columns = [column.id]
  }
}
table "concurrency_settings" {
  schema = schema.public
  column "hash" {
    null = false
    type = bigint
  }
  column "concurrency_key" {
    null = true
    type = character_varying(255)
  }
  column "concurrent_limit" {
    null = true
    type = integer
  }
  column "concurrency_time_window_s" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.hash]
  }
}
table "config" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "config" {
    null    = true
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.name]
  }
}
table "config_change_staging" {
  schema = schema.public
  column "change_id" {
    null    = false
    type    = uuid
    default = sql("gen_random_uuid()")
  }
  column "file_path" {
    null = false
    type = text
  }
  column "operation" {
    null = false
    type = text
  }
  column "key_value" {
    null = false
    type = text
  }
  column "entry_json" {
    null = true
    type = jsonb
  }
  column "submitted_by" {
    null = false
    type = text
  }
  column "context_id" {
    null = false
    type = uuid
  }
  column "submitted_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "merged_at" {
    null = true
    type = timestamptz
  }
  column "status" {
    null    = false
    type    = text
    default = "pending"
  }
  column "status_reason" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.change_id]
  }
  index "idx_config_change_staging_file_status" {
    columns = [column.file_path, column.status, column.submitted_at]
  }
  index "idx_config_change_staging_status_submitted" {
    columns = [column.status, column.submitted_at]
  }
  check "config_change_staging_operation_chk" {
    expr = "(operation = ANY (ARRAY['append'::text, 'update'::text, 'delete'::text]))"
  }
  check "config_change_staging_status_chk" {
    expr = "(status = ANY (ARRAY['pending'::text, 'merged'::text, 'conflict'::text, 'rejected'::text]))"
  }
}
table "custom_concurrency_key_ended" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "ended_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.key, column.ended_at]
  }
}
table "debounce_key" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "job_id" {
    null = false
    type = uuid
  }
  column "previous_job_id" {
    null = true
    type = uuid
  }
  column "first_started_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "debounced_times" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.key]
  }
  index "idx_debounce_key_job_id" {
    columns = [column.job_id]
  }
}
table "debounce_stale_data" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "to_relock" {
    null = true
    type = sql("text[]")
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "debouncing_settings" {
  schema = schema.public
  column "hash" {
    null = false
    type = bigint
  }
  column "debounce_key" {
    null = true
    type = character_varying(255)
  }
  column "debounce_delay_s" {
    null = true
    type = integer
  }
  column "max_total_debouncing_time" {
    null = true
    type = integer
  }
  column "max_total_debounces_amount" {
    null = true
    type = integer
  }
  column "debounce_args_to_accumulate" {
    null = true
    type = sql("text[]")
  }
  primary_key {
    columns = [column.hash]
  }
}
table "dependency_map" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "importer_path" {
    null = false
    type = character_varying(510)
  }
  column "importer_kind" {
    null = false
    type = enum.importer_kind
  }
  column "imported_path" {
    null = false
    type = character_varying(510)
  }
  column "importer_node_id" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "imported_lockfile_hash" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.workspace_id, column.importer_node_id, column.importer_kind, column.importer_path, column.imported_path]
  }
  index "dependency_map_imported_path_idx" {
    columns = [column.workspace_id, column.imported_path]
  }
  index "dependency_map_importer_path_idx" {
    columns = [column.workspace_id, column.importer_path]
  }
}
table "deployment_metadata" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "script_hash" {
    null = true
    type = bigint
  }
  column "app_version" {
    null = true
    type = bigint
  }
  column "callback_job_ids" {
    null = true
    type = sql("uuid[]")
  }
  column "deployment_msg" {
    null = true
    type = text
  }
  column "flow_version" {
    null = true
    type = bigint
  }
  column "job_id" {
    null = true
    type = uuid
  }
  foreign_key "deployment_metadata_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "deployment_metadata_app" {
    unique  = true
    columns = [column.workspace_id, column.path, column.app_version]
    where   = "(app_version IS NOT NULL)"
  }
  index "deployment_metadata_flow" {
    unique  = true
    columns = [column.workspace_id, column.path, column.flow_version]
    where   = "(flow_version IS NOT NULL)"
  }
  index "deployment_metadata_script" {
    unique  = true
    columns = [column.workspace_id, column.script_hash]
    where   = "(script_hash IS NOT NULL)"
  }
}
table "draft" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "typ" {
    null = false
    type = enum.draft_type
  }
  column "value" {
    null = false
    type = json
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.workspace_id, column.path, column.typ]
  }
  foreign_key "draft_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "email_to_igroup" {
  schema = schema.public
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "igroup" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.email, column.igroup]
  }
}
table "email_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "local_part" {
    null = false
    type = character_varying(255)
  }
  column "workspaced_local_part" {
    null = false
    type = boolean
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
}
table "favorite" {
  schema = schema.public
  column "usr" {
    null = false
    type = character_varying(50)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "favorite_kind" {
    null = false
    type = enum.favorite_kind
  }
  primary_key {
    columns = [column.usr, column.workspace_id, column.favorite_kind, column.path]
  }
}
table "flow" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "summary" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "value" {
    null = false
    type = jsonb
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "schema" {
    null = true
    type = json
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "dependency_job" {
    null = true
    type = uuid
  }
  column "draft_only" {
    null = true
    type = boolean
  }
  column "tag" {
    null = true
    type = character_varying(50)
  }
  column "ws_error_handler_muted" {
    null    = false
    type    = boolean
    default = false
  }
  column "dedicated_worker" {
    null = true
    type = boolean
  }
  column "timeout" {
    null = true
    type = integer
  }
  column "visible_to_runner_only" {
    null = true
    type = boolean
  }
  column "concurrency_key" {
    null = true
    type = character_varying(255)
  }
  column "versions" {
    null    = false
    type    = sql("bigint[]")
    default = "{}"
  }
  column "on_behalf_of_email" {
    null = true
    type = text
  }
  column "lock_error_logs" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.workspace_id, column.path]
  }
  foreign_key "flow_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "flow_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  check "proper_id" {
    expr = "((path)::text ~ '^[ufg](\\/[\\w-]+){2,}$'::text)"
  }
}
table "flow_conversation" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("gen_random_uuid()")
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "flow_path" {
    null = false
    type = character_varying(255)
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "flow_conversation_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_flow_conversation_workspace_path" {
    on {
      column = column.workspace_id
    }
    on {
      column = column.flow_path
    }
    on {
      desc   = true
      column = column.updated_at
    }
  }
}
table "flow_conversation_message" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("gen_random_uuid()")
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "message_type" {
    null = false
    type = enum.message_type
  }
  column "content" {
    null = false
    type = text
  }
  column "job_id" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "step_name" {
    null = true
    type = character_varying(255)
  }
  column "success" {
    null    = false
    type    = boolean
    default = true
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "flow_conversation_message_conversation_id_fkey" {
    columns     = [column.conversation_id]
    ref_columns = [table.flow_conversation.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "flow_conversation_message_job_id_fkey" {
    columns     = [column.job_id]
    ref_columns = [table.v2_job.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_conversation_message_conversation_time" {
    on {
      column = column.conversation_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
}
table "flow_iterator_data" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "itered" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "flow_node" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "hash" {
    null = true
    type = bigint
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "lock" {
    null = true
    type = text
  }
  column "code" {
    null = true
    type = text
  }
  column "flow" {
    null = true
    type = jsonb
  }
  column "hash_v2" {
    null    = false
    type    = character(64)
    default = sql("to_hex(nextval('public.flow_node_hash_seq'::regclass))")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "flow_node_path_workspace_id_fkey" {
    columns     = [column.path, column.workspace_id]
    ref_columns = [table.flow.column.path, table.flow.column.workspace_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "flow_node_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "flow_node_hash" {
    columns = [column.hash]
  }
  unique "flow_node_unique_2" {
    columns = [column.path, column.workspace_id, column.hash_v2]
  }
}
table "flow_version" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = jsonb
  }
  column "schema" {
    null = true
    type = json
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "flow_version_workspace_id_path_fkey" {
    columns     = [column.workspace_id, column.path]
    ref_columns = [table.flow.column.workspace_id, table.flow.column.path]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "index_flow_version_path_created_at" {
    columns = [column.path, column.created_at]
  }
}
table "flow_version_lite" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "value" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "flow_version_lite_id_fkey" {
    columns     = [column.id]
    ref_columns = [table.flow_version.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "folder" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "display_name" {
    null = false
    type = character_varying(100)
  }
  column "owners" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "summary" {
    null = true
    type = text
  }
  column "edited_at" {
    null = true
    type = timestamptz
  }
  column "created_by" {
    null = true
    type = character_varying(50)
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
  foreign_key "folder_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "folder_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  index "folder_owners" {
    columns = [column.owners]
    type    = GIN
  }
}
table "folder_permission_history" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "folder_name" {
    null = false
    type = character_varying(255)
  }
  column "changed_by" {
    null = false
    type = character_varying(50)
  }
  column "changed_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "change_type" {
    null = false
    type = character_varying(50)
  }
  column "affected" {
    null = true
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "folder_permission_history_workspace_id_folder_name_fkey" {
    columns     = [column.workspace_id, column.folder_name]
    ref_columns = [table.folder.column.workspace_id, table.folder.column.name]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_folder_perm_history_workspace_folder" {
    on {
      column = column.workspace_id
    }
    on {
      column = column.folder_name
    }
    on {
      desc   = true
      column = column.id
    }
  }
}
table "gcp_trigger" {
  schema = schema.public
  column "gcp_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "topic_id" {
    null = false
    type = character_varying(255)
  }
  column "subscription_id" {
    null = false
    type = character_varying(255)
  }
  column "delivery_type" {
    null = false
    type = enum.delivery_mode
  }
  column "delivery_config" {
    null = true
    type = jsonb
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  column "subscription_mode" {
    null    = false
    type    = enum.gcp_subscription_mode
    default = "create_update"
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "auto_acknowledge_msg" {
    null    = true
    type    = boolean
    default = true
  }
  column "ack_deadline" {
    null = true
    type = integer
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
  index "unique_subscription_per_gcp_resource" {
    unique  = true
    columns = [column.subscription_id, column.gcp_resource_path, column.workspace_id]
  }
  check "gcp_trigger_check" {
    expr = "((delivery_type <> 'push'::public.delivery_mode) OR (delivery_config IS NOT NULL))"
  }
  check "gcp_trigger_subscription_id_check" {
    expr = "((char_length((subscription_id)::text) >= 3) AND (char_length((subscription_id)::text) <= 255))"
  }
  check "gcp_trigger_topic_id_check" {
    expr = "((char_length((topic_id)::text) >= 3) AND (char_length((topic_id)::text) <= 255))"
  }
}
table "global_settings" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = jsonb
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.name]
  }
}
table "group_" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(50)
  }
  column "summary" {
    null = true
    type = text
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
  foreign_key "group__workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "group_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  check "proper_name" {
    expr = "((name)::text ~ '^[\\w-]+$'::text)"
  }
}
table "group_permission_history" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "group_name" {
    null = false
    type = character_varying(255)
  }
  column "changed_by" {
    null = false
    type = character_varying(50)
  }
  column "changed_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "change_type" {
    null = false
    type = character_varying(50)
  }
  column "member_affected" {
    null = true
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "group_permission_history_workspace_id_group_name_fkey" {
    columns     = [column.workspace_id, column.group_name]
    ref_columns = [table.group_.column.workspace_id, table.group_.column.name]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_group_perm_history_workspace_group" {
    on {
      column = column.workspace_id
    }
    on {
      column = column.group_name
    }
    on {
      desc   = true
      column = column.id
    }
  }
}
table "healthchecks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "check_type" {
    null = false
    type = character_varying(50)
  }
  column "healthy" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "healthchecks_check_type_created_at" {
    columns = [column.check_type, column.created_at]
  }
}
table "http_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "route_path" {
    null = false
    type = character_varying(255)
  }
  column "route_path_key" {
    null = false
    type = character_varying(255)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "authentication_method" {
    null    = false
    type    = enum.authentication_method
    default = "none"
  }
  column "http_method" {
    null = false
    type = enum.http_method
  }
  column "static_asset_config" {
    null = true
    type = jsonb
  }
  column "is_static_website" {
    null    = false
    type    = boolean
    default = false
  }
  column "workspaced_route" {
    null    = false
    type    = boolean
    default = false
  }
  column "wrap_body" {
    null    = false
    type    = boolean
    default = false
  }
  column "raw_string" {
    null    = false
    type    = boolean
    default = false
  }
  column "authentication_resource_path" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "summary" {
    null = true
    type = character_varying(512)
  }
  column "description" {
    null = true
    type = text
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "request_type" {
    null    = false
    type    = enum.request_type
    default = "sync"
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
}
table "input" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "runnable_id" {
    null = false
    type = character_varying(255)
  }
  column "runnable_type" {
    null = false
    type = enum.runnable_type
  }
  column "name" {
    null = false
    type = text
  }
  column "args" {
    null = false
    type = jsonb
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "is_public" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "input_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "instance_group" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "summary" {
    null = true
    type = character_varying(2000)
  }
  column "id" {
    null = true
    type = character_varying(1000)
  }
  column "scim_display_name" {
    null = true
    type = character_varying(255)
  }
  column "external_id" {
    null = true
    type = character_varying(512)
  }
  column "instance_role" {
    null    = true
    type    = character_varying(20)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.name]
  }
  check "check_instance_role" {
    expr = "((instance_role)::text = ANY ((ARRAY['devops'::character varying, 'superadmin'::character varying])::text[]))"
  }
}
table "job_logs" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = true
    type = character_varying(255)
  }
  column "created_at" {
    null    = true
    type    = timestamptz
    default = sql("now()")
  }
  column "logs" {
    null = true
    type = text
  }
  column "log_offset" {
    null    = false
    type    = integer
    default = 0
  }
  column "log_file_index" {
    null = true
    type = sql("text[]")
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "job_perms" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "username" {
    null = false
    type = character_varying(50)
  }
  column "is_admin" {
    null = false
    type = boolean
  }
  column "is_operator" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "groups" {
    null = false
    type = sql("text[]")
  }
  column "folders" {
    null = false
    type = sql("jsonb[]")
  }
  column "end_user_email" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "job_result_stream" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = text
  }
  column "stream" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "job_result_stream_v2" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = text
  }
  column "stream" {
    null = false
    type = text
  }
  column "idx" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.job_id, column.idx]
  }
}
table "job_settings" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "runnable_settings" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "job_stats" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "job_id" {
    null = false
    type = uuid
  }
  column "metric_id" {
    null = false
    type = character_varying(50)
  }
  column "metric_name" {
    null = true
    type = character_varying(255)
  }
  column "metric_kind" {
    null = false
    type = enum.metric_kind
  }
  column "scalar_int" {
    null = true
    type = integer
  }
  column "scalar_float" {
    null = true
    type = real
  }
  column "timestamps" {
    null = true
    type = sql("timestamp with time zone[]")
  }
  column "timeseries_int" {
    null = true
    type = sql("integer[]")
  }
  column "timeseries_float" {
    null = true
    type = sql("real[]")
  }
  column "timeseries_start" {
    null = true
    type = timestamptz
  }
  column "offsets_cs" {
    null = true
    type = sql("integer[]")
  }
  primary_key {
    columns = [column.workspace_id, column.job_id, column.metric_id]
  }
  foreign_key "job_stats_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "job_stats_id" {
    columns = [column.job_id]
  }
}
table "kafka_pending_commits" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "kafka_trigger_path" {
    null = false
    type = character_varying(255)
  }
  column "topic" {
    null = false
    type = character_varying(255)
  }
  column "partition" {
    null = false
    type = integer
  }
  column "offset" {
    null = false
    type = bigint
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "kafka_pending_commits_workspace_id_kafka_trigger_path_fkey" {
    columns     = [column.workspace_id, column.kafka_trigger_path]
    ref_columns = [table.kafka_trigger.column.workspace_id, table.kafka_trigger.column.path]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_kafka_pending_commits_trigger" {
    columns = [column.workspace_id, column.kafka_trigger_path]
  }
}
table "kafka_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "kafka_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "topics" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "group_id" {
    null = false
    type = character_varying(255)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "filters" {
    null    = false
    type    = sql("jsonb[]")
    default = "{}"
  }
  column "auto_offset_reset" {
    null    = false
    type    = character_varying(10)
    default = "latest"
  }
  column "reset_offset" {
    null    = false
    type    = boolean
    default = false
  }
  column "auto_commit" {
    null    = false
    type    = boolean
    default = true
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
}
table "lock_hash" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "lockfile_hash" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.workspace_id, column.path]
  }
  foreign_key "lock_hash_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "log_file" {
  schema = schema.public
  column "hostname" {
    null = false
    type = character_varying(255)
  }
  column "log_ts" {
    null = false
    type = timestamp
  }
  column "ok_lines" {
    null = true
    type = bigint
  }
  column "err_lines" {
    null = true
    type = bigint
  }
  column "mode" {
    null = false
    type = enum.log_mode
  }
  column "worker_group" {
    null = true
    type = character_varying(255)
  }
  column "file_path" {
    null = false
    type = character_varying(510)
  }
  column "json_fmt" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.hostname, column.log_ts]
  }
  index "log_file_log_ts_idx" {
    columns = [column.log_ts]
  }
}
table "magic_link" {
  schema = schema.public
  column "email" {
    null = false
    type = character_varying(50)
  }
  column "token" {
    null = false
    type = character_varying(100)
  }
  column "expiration" {
    null    = false
    type    = timestamptz
    default = sql("(now() + '1 day'::interval)")
  }
  primary_key {
    columns = [column.email, column.token]
  }
  index "index_magic_link_exp" {
    columns = [column.expiration]
  }
}
table "mcp_oauth_client" {
  schema = schema.public
  column "mcp_server_url" {
    null = false
    type = text
  }
  column "client_id" {
    null = false
    type = text
  }
  column "client_secret" {
    null = true
    type = text
  }
  column "client_secret_expires_at" {
    null = true
    type = timestamp
  }
  column "token_endpoint" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.mcp_server_url]
  }
  index "idx_mcp_oauth_client_expires" {
    columns = [column.client_secret_expires_at]
  }
}
table "mcp_oauth_refresh_token" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "refresh_token" {
    null = false
    type = character_varying(64)
  }
  column "access_token_hash" {
    null = false
    type = character_varying(64)
  }
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "user_email" {
    null = false
    type = character_varying(255)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "scopes" {
    null = false
    type = sql("text[]")
  }
  column "token_family" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "expires_at" {
    null = false
    type = timestamptz
  }
  column "used_at" {
    null = true
    type = timestamptz
  }
  column "revoked" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "mcp_oauth_refresh_token_client_id_fkey" {
    columns     = [column.client_id]
    ref_columns = [table.mcp_oauth_server_client.column.client_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_mcp_oauth_refresh_token_expires" {
    columns = [column.expires_at]
  }
  index "idx_mcp_oauth_refresh_token_family" {
    columns = [column.token_family]
  }
  index "idx_mcp_oauth_refresh_token_token" {
    columns = [column.refresh_token]
  }
  unique "mcp_oauth_refresh_token_refresh_token_key" {
    columns = [column.refresh_token]
  }
}
table "mcp_oauth_server_client" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "client_name" {
    null = false
    type = character_varying(255)
  }
  column "redirect_uris" {
    null = false
    type = sql("text[]")
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.client_id]
  }
}
table "mcp_oauth_server_code" {
  schema = schema.public
  column "code" {
    null = false
    type = character_varying(64)
  }
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "user_email" {
    null = false
    type = character_varying(255)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "scopes" {
    null = false
    type = sql("text[]")
  }
  column "redirect_uri" {
    null = false
    type = text
  }
  column "code_challenge" {
    null = true
    type = character_varying(128)
  }
  column "code_challenge_method" {
    null = true
    type = character_varying(10)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "expires_at" {
    null    = false
    type    = timestamptz
    default = sql("(now() + '00:10:00'::interval)")
  }
  primary_key {
    columns = [column.code]
  }
  foreign_key "mcp_oauth_server_code_client_id_fkey" {
    columns     = [column.client_id]
    ref_columns = [table.mcp_oauth_server_client.column.client_id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_mcp_oauth_server_code_expires" {
    columns = [column.expires_at]
  }
}
table "metrics" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = jsonb
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("CURRENT_TIMESTAMP")
  }
  index "idx_metrics_id_created_at" {
    where = "((id)::text ~~ 'queue_%'::text)"
    on {
      column = column.id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "metrics_key_idx" {
    columns = [column.id]
  }
  index "metrics_sort_idx" {
    on {
      desc   = true
      column = column.created_at
    }
  }
}
table "mqtt_trigger" {
  schema = schema.public
  column "mqtt_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "subscribe_topics" {
    null = false
    type = sql("jsonb[]")
  }
  column "client_version" {
    null    = false
    type    = enum.mqtt_client_version
    default = "v5"
  }
  column "v5_config" {
    null = true
    type = jsonb
  }
  column "v3_config" {
    null = true
    type = jsonb
  }
  column "client_id" {
    null    = true
    type    = character_varying(65535)
    default = sql("NULL::character varying")
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
}
table "native_trigger" {
  schema = schema.public
  column "external_id" {
    null = false
    type = character_varying(255)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "service_name" {
    null = false
    type = enum.native_trigger_service
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "service_config" {
    null = true
    type = jsonb
  }
  column "error" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "webhook_token_hash" {
    null = false
    type = character_varying(64)
  }
  primary_key {
    columns = [column.external_id, column.workspace_id, column.service_name]
  }
  foreign_key "fk_native_trigger_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_native_trigger_script_path" {
    columns = [column.workspace_id, column.script_path, column.is_flow]
  }
  index "idx_native_trigger_workspace" {
    columns = [column.workspace_id]
  }
}
table "nats_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "nats_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "subjects" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "stream_name" {
    null = true
    type = character_varying(255)
  }
  column "consumer_name" {
    null = true
    type = character_varying(255)
  }
  column "use_jetstream" {
    null = false
    type = boolean
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
  foreign_key "nats_trigger_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "notify_event" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "channel" {
    null = false
    type = text
  }
  column "payload" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
  index "notify_event_created_at_idx" {
    columns = [column.created_at]
  }
}
table "otel_traces" {
  schema = schema.public
  column "trace_id" {
    null = false
    type = bytea
  }
  column "span_id" {
    null = false
    type = bytea
  }
  column "trace_state" {
    null    = false
    type    = text
    default = ""
  }
  column "parent_span_id" {
    null    = false
    type    = bytea
    default = "\\x"
  }
  column "flags" {
    null    = false
    type    = integer
    default = 0
  }
  column "name" {
    null = false
    type = text
  }
  column "kind" {
    null = false
    type = integer
  }
  column "start_time_unix_nano" {
    null = false
    type = bigint
  }
  column "end_time_unix_nano" {
    null = false
    type = bigint
  }
  column "attributes" {
    null    = false
    type    = jsonb
    default = "[]"
  }
  column "dropped_attributes_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "events" {
    null    = false
    type    = jsonb
    default = "[]"
  }
  column "dropped_events_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "links" {
    null    = false
    type    = jsonb
    default = "[]"
  }
  column "dropped_links_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "status" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.trace_id, column.span_id]
  }
  index "otel_traces_time_idx" {
    columns = [column.start_time_unix_nano]
  }
  index "otel_traces_trace_time_idx" {
    columns = [column.trace_id, column.start_time_unix_nano]
  }
}
table "outstanding_wait_time" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "self_wait_time_ms" {
    null = true
    type = bigint
  }
  column "aggregate_wait_time_ms" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.job_id]
  }
}
table "parallel_monitor_lock" {
  schema = schema.public
  column "parent_flow_id" {
    null = false
    type = uuid
  }
  column "job_id" {
    null = false
    type = uuid
  }
  column "last_ping" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.parent_flow_id, column.job_id]
  }
}
table "password" {
  schema = schema.public
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "password_hash" {
    null = true
    type = character_varying(100)
  }
  column "login_type" {
    null = false
    type = character_varying(50)
  }
  column "super_admin" {
    null    = false
    type    = boolean
    default = false
  }
  column "verified" {
    null    = false
    type    = boolean
    default = false
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "company" {
    null = true
    type = character_varying(255)
  }
  column "first_time_user" {
    null    = false
    type    = boolean
    default = false
  }
  column "username" {
    null = true
    type = character_varying(50)
  }
  column "devops" {
    null    = false
    type    = boolean
    default = false
  }
  column "role_source" {
    null    = false
    type    = character_varying(20)
    default = "manual"
  }
  primary_key {
    columns = [column.email]
  }
  check "check_role_source" {
    expr = "((role_source)::text = ANY ((ARRAY['manual'::character varying, 'instance_group'::character varying])::text[]))"
  }
}
table "pending_user" {
  schema = schema.public
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "username" {
    null = false
    type = character_varying(50)
  }
  primary_key {
    columns = [column.email]
  }
}
table "pip_resolution_cache" {
  schema = schema.public
  column "hash" {
    null = false
    type = character_varying(255)
  }
  column "expiration" {
    null = false
    type = timestamp
  }
  column "lockfile" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.hash]
  }
}
table "postgres_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null = true
    type = jsonb
  }
  column "postgres_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "error" {
    null = true
    type = text
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "replication_slot_name" {
    null = false
    type = character_varying(255)
  }
  column "publication_name" {
    null = false
    type = character_varying(255)
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
  foreign_key "fk_postgres_trigger_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "raw_app" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "version" {
    null    = false
    type    = integer
    default = 0
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "summary" {
    null    = false
    type    = character_varying(1000)
    default = ""
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "data" {
    null = false
    type = text
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.path]
  }
  foreign_key "raw_app_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "resource" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = jsonb
  }
  column "description" {
    null = true
    type = text
  }
  column "resource_type" {
    null = false
    type = character_varying(50)
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "edited_at" {
    null = true
    type = timestamptz
  }
  column "created_by" {
    null = true
    type = character_varying(500)
  }
  primary_key {
    columns = [column.workspace_id, column.path]
  }
  foreign_key "resource_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "resource_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  check "proper_id" {
    expr = "((path)::text ~ '^[ufg](\\/[\\w-]+){2,}$'::text)"
  }
}
table "resource_type" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(50)
  }
  column "schema" {
    null = true
    type = jsonb
  }
  column "description" {
    null = true
    type = text
  }
  column "edited_at" {
    null = true
    type = timestamptz
  }
  column "created_by" {
    null = true
    type = character_varying(50)
  }
  column "format_extension" {
    null = true
    type = character_varying(20)
  }
  column "is_fileset" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
  foreign_key "resource_type_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "proper_name" {
    expr = "((name)::text ~ '^[\\w-]+$'::text)"
  }
}
table "resume_job" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "job" {
    null = false
    type = uuid
  }
  column "flow" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "value" {
    null    = false
    type    = jsonb
    default = "null"
  }
  column "approver" {
    null = true
    type = character_varying(1000)
  }
  column "resume_id" {
    null    = false
    type    = integer
    default = 0
  }
  column "approved" {
    null    = false
    type    = boolean
    default = true
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "resume_job_flow_fkey" {
    columns     = [column.flow]
    ref_columns = [table.v2_job_queue.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "runnable_settings" {
  schema = schema.public
  column "hash" {
    null = false
    type = bigint
  }
  column "debouncing_settings" {
    null = true
    type = bigint
  }
  column "concurrency_settings" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.hash]
  }
}
table "schedule" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "edited_by" {
    null = false
    type = character_varying(255)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "schedule" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "args" {
    null = true
    type = jsonb
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "is_flow" {
    null    = false
    type    = boolean
    default = false
  }
  column "email" {
    null    = false
    type    = character_varying(50)
    default = "missing@email.xyz"
  }
  column "error" {
    null = true
    type = text
  }
  column "timezone" {
    null    = false
    type    = character_varying(255)
    default = "UTC"
  }
  column "on_failure" {
    null    = true
    type    = character_varying(1000)
    default = sql("NULL::character varying")
  }
  column "on_recovery" {
    null = true
    type = character_varying(1000)
  }
  column "on_failure_times" {
    null = true
    type = integer
  }
  column "on_failure_exact" {
    null = true
    type = boolean
  }
  column "on_failure_extra_args" {
    null = true
    type = jsonb
  }
  column "on_recovery_times" {
    null = true
    type = integer
  }
  column "on_recovery_extra_args" {
    null = true
    type = jsonb
  }
  column "ws_error_handler_muted" {
    null    = false
    type    = boolean
    default = false
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "summary" {
    null = true
    type = character_varying(512)
  }
  column "no_flow_overlap" {
    null    = false
    type    = boolean
    default = false
  }
  column "tag" {
    null = true
    type = character_varying(50)
  }
  column "paused_until" {
    null = true
    type = timestamptz
  }
  column "on_success" {
    null = true
    type = character_varying(1000)
  }
  column "on_success_extra_args" {
    null = true
    type = jsonb
  }
  column "cron_version" {
    null    = true
    type    = text
    default = "v1"
  }
  column "description" {
    null = true
    type = text
  }
  column "dynamic_skip" {
    null    = true
    type    = character_varying(1000)
    default = sql("NULL::character varying")
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.workspace_id, column.path]
  }
  foreign_key "schedule_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "schedule_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  check "proper_id" {
    expr = "((path)::text ~ '^[ufg](\\/[\\w-]+){2,}$'::text)"
  }
}
table "script" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "hash" {
    null = false
    type = bigint
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "parent_hashes" {
    null = true
    type = sql("bigint[]")
  }
  column "summary" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "content" {
    null = false
    type = text
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "schema" {
    null = true
    type = json
  }
  column "deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_template" {
    null    = true
    type    = boolean
    default = false
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "lock" {
    null = true
    type = text
  }
  column "lock_error_logs" {
    null = true
    type = text
  }
  column "language" {
    null    = false
    type    = enum.script_lang
    default = "python3"
  }
  column "kind" {
    null    = false
    type    = enum.script_kind
    default = "script"
  }
  column "tag" {
    null = true
    type = character_varying(50)
  }
  column "draft_only" {
    null = true
    type = boolean
  }
  column "envs" {
    null = true
    type = sql("character varying(1000)[]")
  }
  column "concurrent_limit" {
    null = true
    type = integer
  }
  column "concurrency_time_window_s" {
    null = true
    type = integer
  }
  column "cache_ttl" {
    null = true
    type = integer
  }
  column "dedicated_worker" {
    null = true
    type = boolean
  }
  column "ws_error_handler_muted" {
    null    = false
    type    = boolean
    default = false
  }
  column "priority" {
    null = true
    type = smallint
  }
  column "timeout" {
    null = true
    type = integer
  }
  column "delete_after_use" {
    null = true
    type = boolean
  }
  column "restart_unless_cancelled" {
    null = true
    type = boolean
  }
  column "concurrency_key" {
    null = true
    type = character_varying(255)
  }
  column "visible_to_runner_only" {
    null = true
    type = boolean
  }
  column "codebase" {
    null = true
    type = character_varying(255)
  }
  column "has_preprocessor" {
    null = true
    type = boolean
  }
  column "on_behalf_of_email" {
    null = true
    type = text
  }
  column "schema_validation" {
    null    = false
    type    = boolean
    default = false
  }
  column "assets" {
    null = true
    type = jsonb
  }
  column "debounce_key" {
    null = true
    type = character_varying(255)
  }
  column "debounce_delay_s" {
    null = true
    type = integer
  }
  column "runnable_settings_handle" {
    null = true
    type = bigint
  }
  column "cache_ignore_s3_path" {
    null = true
    type = boolean
  }
  column "modules" {
    null = true
    type = jsonb
  }
  column "auto_kind" {
    null = true
    type = character_varying(20)
  }
  primary_key {
    columns = [column.workspace_id, column.hash]
  }
  foreign_key "script_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "index_script_on_path_created_at" {
    on {
      column = column.workspace_id
    }
    on {
      column = column.path
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "script_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  index "script_not_archived" {
    where = "(archived = false)"
    on {
      column = column.workspace_id
    }
    on {
      column = column.path
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  check "proper_id" {
    expr = "((path)::text ~ '^[ufg](\\/[\\w-]+){2,}$'::text)"
  }
}
table "skip_workspace_diff_tally" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "added_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.workspace_id]
  }
}
table "sqs_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "queue_url" {
    null = false
    type = character_varying(255)
  }
  column "aws_resource_path" {
    null = false
    type = character_varying(255)
  }
  column "message_attributes" {
    null = true
    type = sql("text[]")
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null = true
    type = jsonb
  }
  column "error" {
    null = true
    type = text
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "aws_auth_resource_type" {
    null    = false
    type    = enum.aws_auth_resource_type
    default = "credentials"
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
  foreign_key "fk_sqs_trigger_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "token" {
  schema = schema.public
  column "token" {
    null = true
    type = character_varying(50)
  }
  column "label" {
    null = true
    type = character_varying(1000)
  }
  column "expiration" {
    null = true
    type = timestamptz
  }
  column "workspace_id" {
    null = true
    type = character_varying(50)
  }
  column "owner" {
    null = true
    type = character_varying(55)
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "super_admin" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "last_used_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "scopes" {
    null = true
    type = sql("text[]")
  }
  column "job" {
    null = true
    type = uuid
  }
  column "token_hash" {
    null = false
    type = character_varying(64)
  }
  column "token_prefix" {
    null = false
    type = character_varying(10)
  }
  primary_key {
    columns = [column.token_hash]
  }
  foreign_key "token_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_token_plaintext" {
    columns = [column.token]
    where   = "(token IS NOT NULL)"
  }
  index "idx_token_prefix" {
    columns = [column.token_prefix]
  }
  index "index_token_exp" {
    columns = [column.expiration]
  }
}
table "token_expiry_notification" {
  schema = schema.public
  column "token_hash" {
    null = false
    type = character_varying(255)
  }
  column "expiration" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.token_hash]
  }
  index "idx_token_expiry_notification_expiration" {
    columns = [column.expiration]
  }
}
table "tutorial_progress" {
  schema = schema.public
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "progress" {
    null    = false
    type    = bit(64)
    default = sql("'0'::\"bit\"")
  }
  column "skipped_all" {
    null    = false
    type    = boolean
    default = false
    comment = "Indicates if the user has skipped all tutorials (vs completing them all)"
  }
  primary_key {
    columns = [column.email]
  }
}
table "unique_ext_jwt_token" {
  schema = schema.public
  column "jwt_hash" {
    null = false
    type = bigint
  }
  column "last_used_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.jwt_hash]
  }
  index "idx_unique_ext_jwt_token_last_used_at" {
    columns = [column.last_used_at]
  }
}
table "usage" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(50)
  }
  column "is_workspace" {
    null = false
    type = boolean
  }
  column "month_" {
    null = false
    type = integer
  }
  column "usage" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id, column.is_workspace, column.month_]
  }
}
table "usr" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "username" {
    null = false
    type = character_varying(50)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "is_admin" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "operator" {
    null    = false
    type    = boolean
    default = false
  }
  column "disabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "role" {
    null = true
    type = character_varying(50)
  }
  column "added_via" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.workspace_id, column.username]
  }
  foreign_key "usr_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_usr_added_via" {
    columns = [column.added_via]
    type    = GIN
  }
  index "index_usr_email" {
    columns = [column.email]
  }
  check "proper_email" {
    expr = "((email)::text ~* '^(?:[a-z0-9!#$%&''*+/=?^_`{|}~-]+(?:\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*|\"(?:[\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f\\x21\\x23-\\x5b\\x5d-\\x7f]|\\\\[\\x01-\\x09\\x0b\\x0c\\x0e-\\x7f])*\")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f\\x21-\\x5a\\x53-\\x7f]|\\\\[\\x01-\\x09\\x0b\\x0c\\x0e-\\x7f])+)\\])$'::text)"
  }
  check "proper_username" {
    expr = "((username)::text ~ '^[\\w-]+$'::text)"
  }
}
table "usr_to_group" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "group_" {
    null = false
    type = character_varying(50)
  }
  column "usr" {
    null    = false
    type    = character_varying(50)
    default = "ruben"
  }
  primary_key {
    columns = [column.workspace_id, column.usr, column.group_]
  }
  foreign_key "fk_group" {
    columns     = [column.workspace_id, column.group_]
    ref_columns = [table.group_.column.workspace_id, table.group_.column.name]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "usr_to_group_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "v2_job" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "raw_code" {
    null = true
    type = text
  }
  column "raw_lock" {
    null = true
    type = text
  }
  column "raw_flow" {
    null = true
    type = jsonb
  }
  column "tag" {
    null    = false
    type    = character_varying(50)
    default = "other"
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null    = false
    type    = character_varying(255)
    default = "missing"
  }
  column "permissioned_as" {
    null    = false
    type    = character_varying(55)
    default = "g/all"
  }
  column "permissioned_as_email" {
    null    = false
    type    = character_varying(255)
    default = "missing@email.xyz"
  }
  column "kind" {
    null    = false
    type    = enum.job_kind
    default = "script"
  }
  column "runnable_id" {
    null = true
    type = bigint
  }
  column "runnable_path" {
    null = true
    type = character_varying(255)
  }
  column "parent_job" {
    null = true
    type = uuid
  }
  column "root_job" {
    null = true
    type = uuid
  }
  column "script_lang" {
    null    = true
    type    = enum.script_lang
    default = "python3"
  }
  column "script_entrypoint_override" {
    null = true
    type = character_varying(255)
  }
  column "flow_step" {
    null = true
    type = integer
  }
  column "flow_step_id" {
    null = true
    type = character_varying(255)
  }
  column "flow_innermost_root_job" {
    null = true
    type = uuid
  }
  column "trigger" {
    null = true
    type = character_varying(255)
  }
  column "trigger_kind" {
    null = true
    type = enum.job_trigger_kind
  }
  column "same_worker" {
    null    = false
    type    = boolean
    default = false
  }
  column "visible_to_owner" {
    null    = false
    type    = boolean
    default = true
  }
  column "concurrent_limit" {
    null = true
    type = integer
  }
  column "concurrency_time_window_s" {
    null = true
    type = integer
  }
  column "cache_ttl" {
    null = true
    type = integer
  }
  column "timeout" {
    null = true
    type = integer
  }
  column "priority" {
    null = true
    type = smallint
  }
  column "preprocessed" {
    null = true
    type = boolean
  }
  column "args" {
    null = true
    type = jsonb
  }
  column "labels" {
    null = true
    type = sql("text[]")
  }
  column "pre_run_error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_job_v2_job_root_by_path_2" {
    columns = [column.workspace_id, column.runnable_path]
    where   = "(parent_job IS NULL)"
  }
  index "ix_job_root_job_index_by_path_2" {
    where = "(parent_job IS NULL)"
    on {
      column = column.workspace_id
    }
    on {
      column = column.runnable_path
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "ix_job_workspace_id_created_at_new_3" {
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "ix_job_workspace_id_created_at_new_5" {
    where = "((kind = ANY (ARRAY['preview'::public.job_kind, 'flowpreview'::public.job_kind])) AND (parent_job IS NULL))"
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "ix_job_workspace_id_created_at_new_8" {
    where = "((kind = 'deploymentcallback'::public.job_kind) AND (parent_job IS NULL))"
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "ix_job_workspace_id_created_at_new_9" {
    where = "((kind = ANY (ARRAY['dependencies'::public.job_kind, 'flowdependencies'::public.job_kind, 'appdependencies'::public.job_kind])) AND (parent_job IS NULL))"
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "ix_v2_job_labels" {
    columns = [column.labels]
    type    = GIN
    where   = "(labels IS NOT NULL)"
  }
  index "ix_v2_job_workspace_id_created_at" {
    where = "((kind = ANY (ARRAY['script'::public.job_kind, 'flow'::public.job_kind, 'singlestepflow'::public.job_kind])) AND (parent_job IS NULL))"
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
}
table "v2_job_completed" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "duration_ms" {
    null = false
    type = bigint
  }
  column "result" {
    null = true
    type = jsonb
  }
  column "deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "canceled_by" {
    null = true
    type = character_varying(50)
  }
  column "canceled_reason" {
    null = true
    type = text
  }
  column "flow_status" {
    null = true
    type = jsonb
  }
  column "started_at" {
    null    = true
    type    = timestamptz
    default = sql("now()")
  }
  column "memory_peak" {
    null = true
    type = integer
  }
  column "status" {
    null = false
    type = enum.job_status
  }
  column "completed_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "worker" {
    null = true
    type = character_varying(255)
  }
  column "workflow_as_code_status" {
    null = true
    type = jsonb
  }
  column "result_columns" {
    null = true
    type = sql("text[]")
  }
  column "retries" {
    null = true
    type = sql("uuid[]")
  }
  column "extras" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "ix_job_completed_completed_at" {
    on {
      desc   = true
      column = column.completed_at
    }
  }
  index "ix_job_workspace_id_completed_at_all" {
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.completed_at
    }
  }
  index "ix_v2_job_completed_failure_workspace" {
    where = "(status = ANY (ARRAY['failure'::public.job_status, 'canceled'::public.job_status]))"
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.completed_at
    }
  }
  index "labeled_jobs_on_jobs" {
    type  = GIN
    where = "(result ? 'wm_labels'::text)"
    on {
      expr = "((result -> 'wm_labels'::text))"
    }
  }
}
table "v2_job_debounce_batch" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "debounce_batch" {
    null = false
    type = bigserial
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_v2_job_debounce_batch_debounce_batch" {
    columns = [column.debounce_batch]
  }
}
table "v2_job_queue" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "started_at" {
    null = true
    type = timestamptz
  }
  column "scheduled_for" {
    null = false
    type = timestamptz
  }
  column "running" {
    null    = false
    type    = boolean
    default = false
  }
  column "canceled_by" {
    null = true
    type = character_varying(255)
  }
  column "canceled_reason" {
    null = true
    type = text
  }
  column "suspend" {
    null    = false
    type    = integer
    default = 0
  }
  column "suspend_until" {
    null = true
    type = timestamptz
  }
  column "tag" {
    null    = false
    type    = character_varying(255)
    default = "other"
  }
  column "priority" {
    null = true
    type = smallint
  }
  column "worker" {
    null = true
    type = character_varying(255)
  }
  column "extras" {
    null = true
    type = jsonb
  }
  column "runnable_settings_handle" {
    null = true
    type = bigint
  }
  column "cache_ignore_s3_path" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "queue_sort_v2" {
    where = "(running = false)"
    on {
      desc       = true
      column     = column.priority
      nulls_last = true
    }
    on {
      column = column.scheduled_for
    }
    on {
      column = column.tag
    }
  }
  index "queue_suspended" {
    where = "(suspend_until IS NOT NULL)"
    on {
      desc       = true
      column     = column.priority
      nulls_last = true
    }
    on {
      column = column.created_at
    }
    on {
      column = column.suspend_until
    }
    on {
      column = column.suspend
    }
    on {
      column = column.tag
    }
  }
  index "root_queue_index_by_path" {
    columns = [column.workspace_id, column.created_at]
  }
  index "v2_job_queue_suspend" {
    columns = [column.workspace_id, column.suspend]
    where   = "(suspend > 0)"
  }
}
table "v2_job_runtime" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "ping" {
    null    = true
    type    = timestamptz
    default = sql("now()")
  }
  column "memory_peak" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "v2_job_runtime_id_fkey" {
    columns     = [column.id]
    ref_columns = [table.v2_job_queue.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "v2_job_status" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "flow_status" {
    null = true
    type = jsonb
  }
  column "flow_leaf_jobs" {
    null = true
    type = jsonb
  }
  column "workflow_as_code_status" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "v2_job_status_id_fkey" {
    columns     = [column.id]
    ref_columns = [table.v2_job_queue.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "variable" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = character_varying(15000)
  }
  column "is_secret" {
    null    = false
    type    = boolean
    default = false
  }
  column "description" {
    null    = false
    type    = character_varying(10000)
    default = ""
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "account" {
    null = true
    type = integer
  }
  column "is_oauth" {
    null    = false
    type    = boolean
    default = false
  }
  column "expires_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.workspace_id, column.path]
  }
  foreign_key "variable_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "variable_extra_perms" {
    columns = [column.extra_perms]
    type    = GIN
  }
  check "proper_id" {
    expr = "((path)::text ~ '^[ufg](\\/[\\w-]+){2,}$'::text)"
  }
}
table "volume" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "size_bytes" {
    null    = false
    type    = bigint
    default = 0
  }
  column "file_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null = false
    type = character_varying(255)
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "updated_by" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null    = false
    type    = text
    default = ""
  }
  column "lease_until" {
    null = true
    type = timestamptz
  }
  column "leased_by" {
    null = true
    type = character_varying(255)
  }
  column "last_used_at" {
    null = true
    type = timestamptz
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
  foreign_key "volume_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_volume_last_used" {
    columns = [column.workspace_id, column.last_used_at]
  }
}
table "websocket_trigger" {
  schema = schema.public
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "url" {
    null = false
    type = character_varying(1000)
  }
  column "script_path" {
    null = false
    type = character_varying(255)
  }
  column "is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "edited_by" {
    null = false
    type = character_varying(50)
  }
  column "edited_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "extra_perms" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "server_id" {
    null = true
    type = character_varying(50)
  }
  column "last_server_ping" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = text
  }
  column "filters" {
    null    = false
    type    = sql("jsonb[]")
    default = "{}"
  }
  column "initial_messages" {
    null    = true
    type    = sql("jsonb[]")
    default = "{}"
  }
  column "url_runnable_args" {
    null    = true
    type    = jsonb
    default = "{}"
  }
  column "can_return_message" {
    null    = false
    type    = boolean
    default = false
  }
  column "error_handler_path" {
    null = true
    type = character_varying(255)
  }
  column "error_handler_args" {
    null = true
    type = jsonb
  }
  column "retry" {
    null = true
    type = jsonb
  }
  column "can_return_error_result" {
    null    = false
    type    = boolean
    default = false
  }
  column "mode" {
    null    = false
    type    = enum.trigger_mode
    default = "enabled"
  }
  column "permissioned_as" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.path, column.workspace_id]
  }
}
table "windmill_migrations" {
  schema = schema.public
  column "name" {
    null = false
    type = text
  }
  column "created_at" {
    null    = true
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.name]
  }
}
table "worker_group_job_stats" {
  schema = schema.public
  column "hour" {
    null = false
    type = bigint
  }
  column "worker_group" {
    null = false
    type = text
  }
  column "script_lang" {
    null = false
    type = character_varying(50)
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "job_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "total_duration_ms" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.hour, column.worker_group, column.script_lang, column.workspace_id]
  }
  foreign_key "worker_group_job_stats_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "worker_group_job_stats_hour_idx" {
    on {
      desc   = true
      column = column.hour
    }
  }
  index "worker_group_job_stats_worker_group_idx" {
    on {
      column = column.worker_group
    }
    on {
      desc   = true
      column = column.hour
    }
  }
  index "worker_group_job_stats_workspace_idx" {
    on {
      column = column.workspace_id
    }
    on {
      desc   = true
      column = column.hour
    }
  }
}
table "worker_ping" {
  schema = schema.public
  column "worker" {
    null = false
    type = character_varying(255)
  }
  column "worker_instance" {
    null = false
    type = character_varying(255)
  }
  column "ping_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "started_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "ip" {
    null    = false
    type    = character_varying(50)
    default = "NO IP"
  }
  column "jobs_executed" {
    null    = false
    type    = integer
    default = 0
  }
  column "custom_tags" {
    null = true
    type = sql("text[]")
  }
  column "worker_group" {
    null    = false
    type    = character_varying(255)
    default = "default"
  }
  column "dedicated_worker" {
    null = true
    type = character_varying(255)
  }
  column "wm_version" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "current_job_id" {
    null = true
    type = uuid
  }
  column "current_job_workspace_id" {
    null = true
    type = character_varying(50)
  }
  column "vcpus" {
    null = true
    type = bigint
  }
  column "memory" {
    null = true
    type = bigint
  }
  column "occupancy_rate" {
    null = true
    type = real
  }
  column "memory_usage" {
    null = true
    type = bigint
  }
  column "wm_memory_usage" {
    null = true
    type = bigint
  }
  column "occupancy_rate_15s" {
    null = true
    type = real
  }
  column "occupancy_rate_5m" {
    null = true
    type = real
  }
  column "occupancy_rate_30m" {
    null = true
    type = real
  }
  column "job_isolation" {
    null = true
    type = text
  }
  column "dedicated_workers" {
    null = true
    type = sql("text[]")
  }
  column "native_mode" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.worker]
  }
  index "worker_ping_on_ping_at" {
    columns = [column.ping_at]
  }
}
table "workspace" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(50)
  }
  column "owner" {
    null = false
    type = character_varying(50)
  }
  column "deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "premium" {
    null    = false
    type    = boolean
    default = false
  }
  column "parent_workspace_id" {
    null = true
    type = character_varying(50)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_parent_workspace_id_fkey" {
    columns     = [column.parent_workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "workspace_parent_idx" {
    columns = [column.parent_workspace_id]
    where   = "(parent_workspace_id IS NOT NULL)"
  }
  check "proper_id" {
    expr = "((id)::text ~ '^\\w+(-\\w+)*$'::text)"
  }
}
table "workspace_dependencies" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "content" {
    null = false
    type = text
  }
  column "language" {
    null = false
    type = enum.script_lang
  }
  column "description" {
    null    = false
    type    = text
    default = ""
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
  index "one_non_archived_per_name_language_constraint" {
    unique  = true
    columns = [column.name, column.language, column.workspace_id]
    where   = "((archived = false) AND (name IS NOT NULL))"
  }
  index "one_non_archived_per_null_name_language_constraint" {
    unique  = true
    columns = [column.language, column.workspace_id]
    where   = "((archived = false) AND (name IS NULL))"
  }
  index "workspace_dependencies_id_workspace" {
    columns = [column.id, column.workspace_id]
  }
  index "workspace_dependencies_workspace_archived_idx" {
    columns = [column.workspace_id, column.archived]
    where   = "(archived = false)"
  }
  index "workspace_dependencies_workspace_lang_name_archived_idx" {
    columns = [column.workspace_id, column.language, column.name, column.archived]
  }
}
table "workspace_diff" {
  schema = schema.public
  column "source_workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "fork_workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "kind" {
    null = false
    type = character_varying(50)
  }
  column "ahead" {
    null    = false
    type    = integer
    default = 0
  }
  column "behind" {
    null    = false
    type    = integer
    default = 0
  }
  column "has_changes" {
    null = true
    type = boolean
  }
  column "exists_in_source" {
    null = true
    type = boolean
  }
  column "exists_in_fork" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.source_workspace_id, column.fork_workspace_id, column.path, column.kind]
  }
}
table "workspace_env" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = character_varying(1000)
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
}
table "workspace_integrations" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "service_name" {
    null = false
    type = enum.native_trigger_service
  }
  column "oauth_data" {
    null = true
    type = jsonb
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "created_by" {
    null = false
    type = character_varying(50)
  }
  column "resource_path" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.workspace_id, column.service_name]
  }
  foreign_key "fk_workspace_integrations_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_workspace_integrations_service" {
    columns = [column.service_name]
  }
  index "idx_workspace_integrations_workspace" {
    columns = [column.workspace_id]
  }
}
table "workspace_invite" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "is_admin" {
    null    = false
    type    = boolean
    default = false
  }
  column "operator" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.workspace_id, column.email]
  }
  foreign_key "workspace_invite_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "proper_email" {
    expr = "((email)::text ~* '^(?:[a-z0-9!#$%&''*+/=?^_`{|}~-]+(?:\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*|\"(?:[\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f\\x21\\x23-\\x5b\\x5d-\\x7f]|\\\\[\\x01-\\x09\\x0b\\x0c\\x0e-\\x7f])*\")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f\\x21-\\x5a\\x53-\\x7f]|\\\\[\\x01-\\x09\\x0b\\x0c\\x0e-\\x7f])+)\\])$'::text)"
  }
}
table "workspace_key" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "kind" {
    null = false
    type = enum.workspace_key_kind
  }
  column "key" {
    null    = false
    type    = character_varying(255)
    default = "changeme"
  }
  primary_key {
    columns = [column.workspace_id, column.kind]
  }
  foreign_key "workspace_key_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "workspace_protection_rule" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "rules" {
    null = false
    type = integer
  }
  column "bypass_groups" {
    null    = false
    type    = sql("text[]")
    default = "{}"
  }
  column "bypass_users" {
    null    = false
    type    = sql("text[]")
    default = "{}"
  }
  column "created_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  primary_key {
    columns = [column.workspace_id, column.name]
  }
  foreign_key "workspace_protection_rule_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "workspace_runnable_dependencies" {
  schema = schema.public
  column "flow_path" {
    null = true
    type = character_varying(255)
  }
  column "runnable_path" {
    null = false
    type = character_varying(255)
  }
  column "script_hash" {
    null = true
    type = bigint
  }
  column "runnable_is_flow" {
    null = false
    type = boolean
  }
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "app_path" {
    null = true
    type = character_varying(255)
  }
  foreign_key "fk_workspace_runnable_dependencies_app_path" {
    columns     = [column.app_path, column.workspace_id]
    ref_columns = [table.app.column.path, table.app.column.workspace_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "flow_workspace_runnables_workspace_id_flow_path_fkey" {
    columns     = [column.flow_path, column.workspace_id]
    ref_columns = [table.flow.column.path, table.flow.column.workspace_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "app_workspace_with_hash_unique_idx" {
    unique  = true
    columns = [column.app_path, column.runnable_path, column.script_hash, column.runnable_is_flow, column.workspace_id]
    where   = "(script_hash IS NOT NULL)"
  }
  index "app_workspace_without_hash_unique_idx" {
    unique  = true
    columns = [column.app_path, column.runnable_path, column.runnable_is_flow, column.workspace_id]
    where   = "(script_hash IS NULL)"
  }
  index "flow_workspace_runnable_path_is_flow_idx" {
    columns = [column.runnable_path, column.runnable_is_flow, column.workspace_id]
  }
  index "flow_workspace_with_hash_unique_idx" {
    unique  = true
    columns = [column.flow_path, column.runnable_path, column.script_hash, column.runnable_is_flow, column.workspace_id]
    where   = "(script_hash IS NOT NULL)"
  }
  index "flow_workspace_without_hash_unique_idx" {
    unique  = true
    columns = [column.flow_path, column.runnable_path, column.runnable_is_flow, column.workspace_id]
    where   = "(script_hash IS NULL)"
  }
  check "workspace_runnable_dependencies_path_exclusive" {
    expr = "(((flow_path IS NOT NULL) AND (app_path IS NULL)) OR ((flow_path IS NULL) AND (app_path IS NOT NULL)))"
  }
}
table "workspace_settings" {
  schema = schema.public
  column "workspace_id" {
    null = false
    type = character_varying(50)
  }
  column "slack_team_id" {
    null = true
    type = character_varying(50)
  }
  column "slack_name" {
    null = true
    type = character_varying(50)
  }
  column "slack_command_script" {
    null = true
    type = character_varying(255)
  }
  column "slack_email" {
    null    = false
    type    = character_varying(50)
    default = "missing@email.xyz"
  }
  column "customer_id" {
    null = true
    type = character_varying(100)
  }
  column "plan" {
    null = true
    type = character_varying(40)
  }
  column "webhook" {
    null = true
    type = text
  }
  column "deploy_to" {
    null = true
    type = character_varying(255)
  }
  column "ai_config" {
    null = true
    type = jsonb
  }
  column "large_file_storage" {
    null = true
    type = jsonb
  }
  column "git_sync" {
    null = true
    type = jsonb
  }
  column "default_app" {
    null = true
    type = character_varying(255)
  }
  column "default_scripts" {
    null = true
    type = jsonb
  }
  column "deploy_ui" {
    null = true
    type = jsonb
  }
  column "mute_critical_alerts" {
    null = true
    type = boolean
  }
  column "color" {
    null    = true
    type    = character_varying(7)
    default = sql("NULL::character varying")
  }
  column "operator_settings" {
    null    = true
    type    = jsonb
    default = "{\"runs\": true, \"groups\": true, \"folders\": true, \"workers\": true, \"triggers\": true, \"resources\": true, \"schedules\": true, \"variables\": true, \"audit_logs\": true}"
  }
  column "teams_command_script" {
    null = true
    type = text
  }
  column "teams_team_id" {
    null = true
    type = text
  }
  column "teams_team_name" {
    null = true
    type = text
  }
  column "git_app_installations" {
    null    = false
    type    = jsonb
    default = "[]"
  }
  column "ducklake" {
    null = true
    type = jsonb
  }
  column "slack_oauth_client_id" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "slack_oauth_client_secret" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "datatable" {
    null = true
    type = jsonb
  }
  column "teams_team_guid" {
    null = true
    type = text
  }
  column "auto_invite" {
    null = true
    type = jsonb
  }
  column "error_handler" {
    null = true
    type = jsonb
  }
  column "success_handler" {
    null = true
    type = jsonb
  }
  column "public_app_execution_limit_per_minute" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.workspace_id]
  }
  foreign_key "workspace_settings_workspace_id_fkey" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspace.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_workspace_settings_auto_invite" {
    columns = [column.auto_invite]
    type    = GIN
  }
}
table "zombie_job_counter" {
  schema = schema.public
  column "job_id" {
    null = false
    type = uuid
  }
  column "counter" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.job_id]
  }
  foreign_key "zombie_job_counter_job_id_fkey" {
    columns     = [column.job_id]
    ref_columns = [table.v2_job.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "snapshots" {
  schema = schema.world_state
  column "id" {
    null = false
    type = bigserial
  }
  column "surface" {
    null = false
    type = text
  }
  column "collected_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "stale" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "snapshots_surface_fkey" {
    columns     = [column.surface]
    ref_columns = [table.surface_config.column.surface]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_world_state_snapshots_surface_collected_at" {
    on {
      column = column.surface
    }
    on {
      desc   = true
      column = column.collected_at
    }
    on {
      desc   = true
      column = column.id
    }
  }
}
table "surface_config" {
  schema = schema.world_state
  column "surface" {
    null = false
    type = text
  }
  column "refresh_interval_seconds" {
    null = false
    type = integer
  }
  column "stale_threshold_seconds" {
    null = false
    type = integer
  }
  column "summary" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.surface]
  }
  check "surface_config_refresh_interval_seconds_check" {
    expr = "(refresh_interval_seconds > 0)"
  }
  check "surface_config_stale_threshold_seconds_check" {
    expr = "(stale_threshold_seconds > 0)"
  }
}
enum "job_kind" {
  schema = schema.public
  values = ["script", "preview", "flow", "dependencies", "flowpreview", "script_hub", "identity", "flowdependencies", "http", "graphql", "postgresql", "noop", "appdependencies", "deploymentcallback", "singlestepflow", "flowscript", "flownode", "appscript", "aiagent", "unassigned_script", "unassigned_flow", "unassigned_singlestepflow"]
}
enum "login_type" {
  schema = schema.public
  values = ["password", "github"]
}
enum "action_kind" {
  schema = schema.public
  values = ["create", "update", "delete", "execute"]
}
enum "workspace_key_kind" {
  schema = schema.public
  values = ["cloud"]
}
enum "script_lang" {
  schema = schema.public
  values = ["python3", "deno", "go", "bash", "postgresql", "nativets", "bun", "mysql", "bigquery", "snowflake", "graphql", "powershell", "mssql", "php", "bunnative", "rust", "ansible", "csharp", "oracledb", "nu", "java", "duckdb", "ruby"]
}
enum "script_kind" {
  schema = schema.public
  values = ["script", "trigger", "failure", "command", "approval", "preprocessor"]
}
enum "favorite_kind" {
  schema = schema.public
  values = ["app", "script", "flow", "raw_app", "asset"]
}
enum "runnable_type" {
  schema = schema.public
  values = ["ScriptHash", "ScriptPath", "FlowPath"]
}
enum "draft_type" {
  schema = schema.public
  values = ["script", "flow", "app"]
}
enum "importer_kind" {
  schema = schema.public
  values = ["script", "flow", "app"]
}
enum "metric_kind" {
  schema = schema.public
  values = ["scalar_int", "scalar_float", "timeseries_int", "timeseries_float"]
}
enum "log_mode" {
  schema = schema.public
  values = ["standalone", "server", "worker", "agent", "indexer", "mcp"]
}
enum "http_method" {
  schema = schema.public
  values = ["get", "post", "put", "delete", "patch"]
}
enum "autoscaling_event_type" {
  schema = schema.public
  values = ["full_scaleout", "scalein", "scaleout"]
}
enum "trigger_kind" {
  schema = schema.public
  values = ["webhook", "http", "websocket", "kafka", "email", "nats", "postgres", "sqs", "mqtt", "gcp", "default_email", "nextcloud", "google"]
}
enum "job_status" {
  schema = schema.public
  values = ["success", "failure", "canceled", "skipped"]
}
enum "job_trigger_kind" {
  schema = schema.public
  values = ["webhook", "http", "websocket", "kafka", "email", "nats", "schedule", "app", "ui", "postgres", "sqs", "gcp", "mqtt", "nextcloud", "google"]
}
enum "mqtt_client_version" {
  schema = schema.public
  values = ["v3", "v5"]
}
enum "authentication_method" {
  schema = schema.public
  values = ["none", "windmill", "api_key", "basic_http", "custom_script", "signature"]
}
enum "delivery_mode" {
  schema = schema.public
  values = ["push", "pull"]
}
enum "aws_auth_resource_type" {
  schema = schema.public
  values = ["oidc", "credentials"]
}
enum "gcp_subscription_mode" {
  schema = schema.public
  values = ["create_update", "existing"]
}
enum "asset_usage_kind" {
  schema = schema.public
  values = ["script", "flow", "job"]
}
enum "asset_access_type" {
  schema = schema.public
  values = ["r", "w", "rw"]
}
enum "asset_kind" {
  schema = schema.public
  values = ["s3object", "resource", "variable", "ducklake", "datatable", "volume"]
}
enum "message_type" {
  schema = schema.public
  values = ["user", "assistant", "tool"]
}
enum "request_type" {
  schema = schema.public
  values = ["sync", "async", "sync_sse"]
}
enum "trigger_mode" {
  schema = schema.public
  values = ["enabled", "disabled", "suspended"]
}
enum "native_trigger_service" {
  schema = schema.public
  values = ["nextcloud", "google"]
}
schema "graph" {
}
schema "memory" {
}
schema "platform" {
}
schema "public" {
  comment = "standard public schema"
}
schema "world_state" {
}
