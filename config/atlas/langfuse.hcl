Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "Account" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "provider" {
    null = false
    type = text
  }
  column "providerAccountId" {
    null = false
    type = text
  }
  column "refresh_token" {
    null = true
    type = text
  }
  column "access_token" {
    null = true
    type = text
  }
  column "expires_at" {
    null = true
    type = integer
  }
  column "token_type" {
    null = true
    type = text
  }
  column "scope" {
    null = true
    type = text
  }
  column "id_token" {
    null = true
    type = text
  }
  column "session_state" {
    null = true
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "expires_in" {
    null = true
    type = integer
  }
  column "ext_expires_in" {
    null = true
    type = integer
  }
  column "refresh_token_expires_in" {
    null = true
    type = integer
  }
  column "created_at" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "Account_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "Account_provider_providerAccountId_key" {
    unique  = true
    columns = [column.provider, column.providerAccountId]
  }
  index "Account_user_id_idx" {
    columns = [column.user_id]
  }
}
table "Session" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "expires" {
    null = false
    type = timestamp(3)
  }
  column "session_token" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "Session_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "Session_session_token_key" {
    unique  = true
    columns = [column.session_token]
  }
}
table "_prisma_migrations" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "checksum" {
    null = false
    type = character_varying(64)
  }
  column "finished_at" {
    null = true
    type = timestamptz
  }
  column "migration_name" {
    null = false
    type = character_varying(255)
  }
  column "logs" {
    null = true
    type = text
  }
  column "rolled_back_at" {
    null = true
    type = timestamptz
  }
  column "started_at" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "applied_steps_count" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
}
table "actions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = enum.ActionType
  }
  column "config" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "actions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "actions_project_id_idx" {
    columns = [column.project_id]
  }
}
table "annotation_queue_assignments" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "queue_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "annotation_queue_assignments_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "annotation_queue_assignments_queue_id_fkey" {
    columns     = [column.queue_id]
    ref_columns = [table.annotation_queues.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "annotation_queue_assignments_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "annotation_queue_assignments_project_id_queue_id_user_id_key" {
    unique  = true
    columns = [column.project_id, column.queue_id, column.user_id]
  }
}
table "annotation_queue_items" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "queue_id" {
    null = false
    type = text
  }
  column "object_id" {
    null = false
    type = text
  }
  column "object_type" {
    null = false
    type = enum.AnnotationQueueObjectType
  }
  column "status" {
    null    = false
    type    = enum.AnnotationQueueStatus
    default = "PENDING"
  }
  column "locked_at" {
    null = true
    type = timestamp(3)
  }
  column "locked_by_user_id" {
    null = true
    type = text
  }
  column "annotator_user_id" {
    null = true
    type = text
  }
  column "completed_at" {
    null = true
    type = timestamp(3)
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "annotation_queue_items_annotator_user_id_fkey" {
    columns     = [column.annotator_user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "annotation_queue_items_locked_by_user_id_fkey" {
    columns     = [column.locked_by_user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "annotation_queue_items_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "annotation_queue_items_queue_id_fkey" {
    columns     = [column.queue_id]
    ref_columns = [table.annotation_queues.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "annotation_queue_items_annotator_user_id_idx" {
    columns = [column.annotator_user_id]
  }
  index "annotation_queue_items_created_at_idx" {
    columns = [column.created_at]
  }
  index "annotation_queue_items_id_project_id_idx" {
    columns = [column.id, column.project_id]
  }
  index "annotation_queue_items_object_id_object_type_project_id_que_idx" {
    columns = [column.object_id, column.object_type, column.project_id, column.queue_id]
  }
  index "annotation_queue_items_project_id_queue_id_status_idx" {
    columns = [column.project_id, column.queue_id, column.status]
  }
}
table "annotation_queues" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = true
    type = text
  }
  column "score_config_ids" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "annotation_queues_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "annotation_queues_id_project_id_idx" {
    columns = [column.id, column.project_id]
  }
  index "annotation_queues_project_id_created_at_idx" {
    columns = [column.project_id, column.created_at]
  }
  index "annotation_queues_project_id_name_key" {
    unique  = true
    columns = [column.project_id, column.name]
  }
}
table "api_keys" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "note" {
    null = true
    type = text
  }
  column "public_key" {
    null = false
    type = text
  }
  column "hashed_secret_key" {
    null = false
    type = text
  }
  column "display_secret_key" {
    null = false
    type = text
  }
  column "last_used_at" {
    null = true
    type = timestamp(3)
  }
  column "expires_at" {
    null = true
    type = timestamp(3)
  }
  column "project_id" {
    null = true
    type = text
  }
  column "fast_hashed_secret_key" {
    null = true
    type = text
  }
  column "organization_id" {
    null = true
    type = text
  }
  column "scope" {
    null    = false
    type    = enum.ApiKeyScope
    default = "PROJECT"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "api_keys_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "api_keys_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "api_keys_fast_hashed_secret_key_idx" {
    columns = [column.fast_hashed_secret_key]
  }
  index "api_keys_fast_hashed_secret_key_key" {
    unique  = true
    columns = [column.fast_hashed_secret_key]
  }
  index "api_keys_hashed_secret_key_idx" {
    columns = [column.hashed_secret_key]
  }
  index "api_keys_hashed_secret_key_key" {
    unique  = true
    columns = [column.hashed_secret_key]
  }
  index "api_keys_id_key" {
    unique  = true
    columns = [column.id]
  }
  index "api_keys_organization_id_idx" {
    columns = [column.organization_id]
  }
  index "api_keys_project_id_idx" {
    columns = [column.project_id]
  }
  index "api_keys_public_key_idx" {
    columns = [column.public_key]
  }
  index "api_keys_public_key_key" {
    unique  = true
    columns = [column.public_key]
  }
}
table "audit_logs" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "user_id" {
    null = true
    type = text
  }
  column "project_id" {
    null = true
    type = text
  }
  column "resource_type" {
    null = false
    type = text
  }
  column "resource_id" {
    null = false
    type = text
  }
  column "action" {
    null = false
    type = text
  }
  column "before" {
    null = true
    type = text
  }
  column "after" {
    null = true
    type = text
  }
  column "org_id" {
    null = false
    type = text
  }
  column "user_org_role" {
    null = true
    type = text
  }
  column "user_project_role" {
    null = true
    type = text
  }
  column "api_key_id" {
    null = true
    type = text
  }
  column "type" {
    null    = false
    type    = enum.AuditLogRecordType
    default = "USER"
  }
  primary_key {
    columns = [column.id]
  }
  index "audit_logs_api_key_id_idx" {
    columns = [column.api_key_id]
  }
  index "audit_logs_created_at_idx" {
    columns = [column.created_at]
  }
  index "audit_logs_org_id_idx" {
    columns = [column.org_id]
  }
  index "audit_logs_project_id_idx" {
    columns = [column.project_id]
  }
  index "audit_logs_updated_at_idx" {
    columns = [column.updated_at]
  }
  index "audit_logs_user_id_idx" {
    columns = [column.user_id]
  }
}
table "automation_executions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "source_id" {
    null = false
    type = text
  }
  column "automation_id" {
    null = false
    type = text
  }
  column "trigger_id" {
    null = false
    type = text
  }
  column "action_id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "status" {
    null    = false
    type    = enum.ActionExecutionStatus
    default = "PENDING"
  }
  column "input" {
    null = false
    type = jsonb
  }
  column "output" {
    null = true
    type = jsonb
  }
  column "started_at" {
    null = true
    type = timestamp(3)
  }
  column "finished_at" {
    null = true
    type = timestamp(3)
  }
  column "error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "automation_executions_action_id_fkey" {
    columns     = [column.action_id]
    ref_columns = [table.actions.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "automation_executions_automation_id_fkey" {
    columns     = [column.automation_id]
    ref_columns = [table.automations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "automation_executions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "automation_executions_trigger_id_fkey" {
    columns     = [column.trigger_id]
    ref_columns = [table.triggers.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "automation_executions_action_id_idx" {
    columns = [column.action_id]
  }
  index "automation_executions_project_id_idx" {
    columns = [column.project_id]
  }
  index "automation_executions_trigger_id_idx" {
    columns = [column.trigger_id]
  }
}
table "automations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "trigger_id" {
    null = false
    type = text
  }
  column "action_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "automations_action_id_fkey" {
    columns     = [column.action_id]
    ref_columns = [table.actions.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "automations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "automations_trigger_id_fkey" {
    columns     = [column.trigger_id]
    ref_columns = [table.triggers.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "automations_project_id_action_id_trigger_id_idx" {
    columns = [column.project_id, column.action_id, column.trigger_id]
  }
  index "automations_project_id_name_idx" {
    columns = [column.project_id, column.name]
  }
}
table "background_migrations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "script" {
    null = false
    type = text
  }
  column "args" {
    null = false
    type = jsonb
  }
  column "finished_at" {
    null = true
    type = timestamp(3)
  }
  column "failed_at" {
    null = true
    type = timestamp(3)
  }
  column "failed_reason" {
    null = true
    type = text
  }
  column "worker_id" {
    null = true
    type = text
  }
  column "locked_at" {
    null = true
    type = timestamp(3)
  }
  column "state" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  index "background_migrations_name_key" {
    unique  = true
    columns = [column.name]
  }
}
table "batch_actions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "action_type" {
    null = false
    type = text
  }
  column "table_name" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = text
  }
  column "finished_at" {
    null = true
    type = timestamp(3)
  }
  column "query" {
    null = false
    type = jsonb
  }
  column "config" {
    null = true
    type = jsonb
  }
  column "total_count" {
    null = true
    type = integer
  }
  column "processed_count" {
    null = true
    type = integer
  }
  column "failed_count" {
    null = true
    type = integer
  }
  column "log" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "batch_actions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "batch_actions_project_id_action_type_idx" {
    columns = [column.project_id, column.action_type]
  }
  index "batch_actions_project_id_user_id_idx" {
    columns = [column.project_id, column.user_id]
  }
  index "batch_actions_status_idx" {
    columns = [column.status]
  }
}
table "batch_exports" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "finished_at" {
    null = true
    type = timestamp(3)
  }
  column "expires_at" {
    null = true
    type = timestamp(3)
  }
  column "name" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = text
  }
  column "query" {
    null = false
    type = jsonb
  }
  column "format" {
    null = false
    type = text
  }
  column "url" {
    null = true
    type = text
  }
  column "log" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "batch_exports_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "batch_exports_project_id_user_id_idx" {
    columns = [column.project_id, column.user_id]
  }
  index "batch_exports_status_idx" {
    columns = [column.status]
  }
}
table "billing_meter_backups" {
  schema = schema.public
  column "stripe_customer_id" {
    null = false
    type = text
  }
  column "meter_id" {
    null = false
    type = text
  }
  column "start_time" {
    null = false
    type = timestamp(3)
  }
  column "end_time" {
    null = false
    type = timestamp(3)
  }
  column "aggregated_value" {
    null = false
    type = integer
  }
  column "event_name" {
    null = false
    type = text
  }
  column "org_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  index "billing_meter_backups_stripe_customer_id_meter_id_start_tim_idx" {
    columns = [column.stripe_customer_id, column.meter_id, column.start_time, column.end_time]
  }
  index "billing_meter_backups_stripe_customer_id_meter_id_start_tim_key" {
    unique  = true
    columns = [column.stripe_customer_id, column.meter_id, column.start_time, column.end_time]
  }
}
table "blob_storage_integrations" {
  schema = schema.public
  column "project_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = enum.BlobStorageIntegrationType
  }
  column "bucket_name" {
    null = false
    type = text
  }
  column "prefix" {
    null = false
    type = text
  }
  column "access_key_id" {
    null = true
    type = text
  }
  column "secret_access_key" {
    null = true
    type = text
  }
  column "region" {
    null = false
    type = text
  }
  column "endpoint" {
    null = true
    type = text
  }
  column "force_path_style" {
    null = false
    type = boolean
  }
  column "next_sync_at" {
    null = true
    type = timestamp(3)
  }
  column "last_sync_at" {
    null = true
    type = timestamp(3)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "export_frequency" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "file_type" {
    null    = false
    type    = enum.BlobStorageIntegrationFileType
    default = "CSV"
  }
  column "export_mode" {
    null    = false
    type    = enum.BlobStorageExportMode
    default = "FULL_HISTORY"
  }
  column "export_start_date" {
    null = true
    type = timestamp(3)
  }
  column "export_source" {
    null    = false
    type    = enum.AnalyticsIntegrationExportSource
    default = "TRACES_OBSERVATIONS"
  }
  column "last_error" {
    null = true
    type = text
  }
  column "last_error_at" {
    null = true
    type = timestamp(3)
  }
  column "last_failure_notification_sent_at" {
    null = true
    type = timestamp(3)
  }
  column "compressed" {
    null    = false
    type    = boolean
    default = true
  }
  primary_key {
    columns = [column.project_id]
  }
  foreign_key "blob_storage_integrations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "cloud_spend_alerts" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "org_id" {
    null = false
    type = text
  }
  column "title" {
    null = false
    type = text
  }
  column "threshold" {
    null = false
    type = numeric(65,30)
  }
  column "triggered_at" {
    null = true
    type = timestamp(3)
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "cloud_spend_alerts_org_id_fkey" {
    columns     = [column.org_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "cloud_spend_alerts_org_id_idx" {
    columns = [column.org_id]
  }
}
table "comment_reactions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "comment_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "emoji" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "comment_reactions_comment_id_fkey" {
    columns     = [column.comment_id]
    ref_columns = [table.comments.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "comment_reactions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "comment_reactions_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "comment_reactions_comment_id_user_id_emoji_key" {
    unique  = true
    columns = [column.comment_id, column.user_id, column.emoji]
  }
}
table "comments" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "object_type" {
    null = false
    type = enum.CommentObjectType
  }
  column "object_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "content" {
    null = false
    type = text
  }
  column "author_user_id" {
    null = true
    type = text
  }
  column "data_field" {
    null = true
    type = text
  }
  column "path" {
    null    = true
    type    = sql("text[]")
    default = "{}"
  }
  column "range_start" {
    null    = true
    type    = sql("integer[]")
    default = "{}"
  }
  column "range_end" {
    null    = true
    type    = sql("integer[]")
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "comments_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "comments_project_id_object_type_object_id_idx" {
    columns = [column.project_id, column.object_type, column.object_id]
  }
  index "idx_comments_content_gin" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, content)"
    }
  }
}
table "cron_jobs" {
  schema = schema.public
  column "name" {
    null = false
    type = text
  }
  column "last_run" {
    null = true
    type = timestamp(3)
  }
  column "state" {
    null = true
    type = text
  }
  column "job_started_at" {
    null = true
    type = timestamp(3)
  }
  primary_key {
    columns = [column.name]
  }
}
table "dashboard_widgets" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "created_by" {
    null = true
    type = text
  }
  column "updated_by" {
    null = true
    type = text
  }
  column "project_id" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "view" {
    null = false
    type = enum.DashboardWidgetViews
  }
  column "dimensions" {
    null = false
    type = jsonb
  }
  column "metrics" {
    null = false
    type = jsonb
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "chart_type" {
    null = false
    type = enum.DashboardWidgetChartType
  }
  column "chart_config" {
    null = false
    type = jsonb
  }
  column "min_version" {
    null    = false
    type    = integer
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dashboard_widgets_created_by_fkey" {
    columns     = [column.created_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "dashboard_widgets_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "dashboard_widgets_updated_by_fkey" {
    columns     = [column.updated_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
}
table "dashboards" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "created_by" {
    null = true
    type = text
  }
  column "updated_by" {
    null = true
    type = text
  }
  column "project_id" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "definition" {
    null = false
    type = jsonb
  }
  column "filters" {
    null    = false
    type    = jsonb
    default = "[]"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dashboards_created_by_fkey" {
    columns     = [column.created_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "dashboards_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "dashboards_updated_by_fkey" {
    columns     = [column.updated_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
}
table "dataset_items" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "input" {
    null = true
    type = jsonb
  }
  column "expected_output" {
    null = true
    type = jsonb
  }
  column "source_observation_id" {
    null = true
    type = text
  }
  column "dataset_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "status" {
    null    = true
    type    = enum.DatasetStatus
    default = "ACTIVE"
  }
  column "source_trace_id" {
    null = true
    type = text
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "project_id" {
    null = false
    type = text
  }
  column "is_deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "valid_from" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "valid_to" {
    null = true
    type = timestamp(3)
  }
  primary_key {
    columns = [column.id, column.project_id, column.valid_from]
  }
  foreign_key "dataset_items_dataset_id_project_id_fkey" {
    columns     = [column.dataset_id, column.project_id]
    ref_columns = [table.datasets.column.id, table.datasets.column.project_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "dataset_items_created_at_idx" {
    columns = [column.created_at]
  }
  index "dataset_items_dataset_id_idx" {
    columns = [column.dataset_id]
    type    = HASH
  }
  index "dataset_items_project_id_id_valid_from_idx" {
    columns = [column.project_id, column.id, column.valid_from]
  }
  index "dataset_items_project_id_valid_to_idx" {
    columns = [column.project_id, column.valid_to]
  }
  index "dataset_items_source_observation_id_idx" {
    columns = [column.source_observation_id]
    type    = HASH
  }
  index "dataset_items_source_trace_id_idx" {
    columns = [column.source_trace_id]
    type    = HASH
  }
  index "dataset_items_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "dataset_run_items" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "dataset_run_id" {
    null = false
    type = text
  }
  column "dataset_item_id" {
    null = false
    type = text
  }
  column "observation_id" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "trace_id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id, column.project_id]
  }
  foreign_key "dataset_run_items_dataset_run_id_project_id_fkey" {
    columns     = [column.dataset_run_id, column.project_id]
    ref_columns = [table.dataset_runs.column.id, table.dataset_runs.column.project_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "dataset_run_items_created_at_idx" {
    columns = [column.created_at]
  }
  index "dataset_run_items_dataset_item_id_idx" {
    columns = [column.dataset_item_id]
    type    = HASH
  }
  index "dataset_run_items_dataset_run_id_idx" {
    columns = [column.dataset_run_id]
    type    = HASH
  }
  index "dataset_run_items_observation_id_idx" {
    columns = [column.observation_id]
    type    = HASH
  }
  index "dataset_run_items_trace_id_idx" {
    columns = [column.trace_id]
  }
  index "dataset_run_items_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "dataset_runs" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "dataset_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "description" {
    null = true
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id, column.project_id]
  }
  foreign_key "dataset_runs_dataset_id_project_id_fkey" {
    columns     = [column.dataset_id, column.project_id]
    ref_columns = [table.datasets.column.id, table.datasets.column.project_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "dataset_runs_created_at_idx" {
    columns = [column.created_at]
  }
  index "dataset_runs_dataset_id_idx" {
    columns = [column.dataset_id]
    type    = HASH
  }
  index "dataset_runs_dataset_id_project_id_name_key" {
    unique  = true
    columns = [column.dataset_id, column.project_id, column.name]
  }
  index "dataset_runs_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "datasets" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "description" {
    null = true
    type = text
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "remote_experiment_payload" {
    null = true
    type = jsonb
  }
  column "remote_experiment_url" {
    null = true
    type = text
  }
  column "expected_output_schema" {
    null = true
    type = json
  }
  column "input_schema" {
    null = true
    type = json
  }
  primary_key {
    columns = [column.id, column.project_id]
  }
  foreign_key "datasets_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "datasets_created_at_idx" {
    columns = [column.created_at]
  }
  index "datasets_project_id_name_key" {
    unique  = true
    columns = [column.project_id, column.name]
  }
  index "datasets_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "default_llm_models" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "llm_api_key_id" {
    null = false
    type = text
  }
  column "provider" {
    null = false
    type = text
  }
  column "adapter" {
    null = false
    type = text
  }
  column "model" {
    null = false
    type = text
  }
  column "model_params" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "default_llm_models_llm_api_key_id_fkey" {
    columns     = [column.llm_api_key_id]
    ref_columns = [table.llm_api_keys.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "default_llm_models_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  unique "default_llm_models_project_id_key" {
    columns = [column.project_id]
  }
}
table "default_views" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = true
    type = text
  }
  column "view_name" {
    null = false
    type = text
  }
  column "view_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "default_views_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "default_views_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "default_views_project_id_view_name_idx" {
    columns = [column.project_id, column.view_name]
  }
  index "default_views_project_user_view_key" {
    unique  = true
    columns = [column.project_id, column.user_id, column.view_name]
    where   = "(user_id IS NOT NULL)"
  }
  index "default_views_project_view_key" {
    unique  = true
    columns = [column.project_id, column.view_name]
    where   = "(user_id IS NULL)"
  }
}
table "eval_templates" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = integer
  }
  column "prompt" {
    null = false
    type = text
  }
  column "model" {
    null = true
    type = text
  }
  column "model_params" {
    null = true
    type = jsonb
  }
  column "vars" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "output_schema" {
    null = false
    type = jsonb
  }
  column "provider" {
    null = true
    type = text
  }
  column "partner" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "eval_templates_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "eval_templates_project_id_id_idx" {
    columns = [column.project_id, column.id]
  }
  index "eval_templates_project_id_name_version_key" {
    unique  = true
    columns = [column.project_id, column.name, column.version]
  }
}
table "job_configurations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "job_type" {
    null = false
    type = enum.JobType
  }
  column "eval_template_id" {
    null = true
    type = text
  }
  column "score_name" {
    null = false
    type = text
  }
  column "filter" {
    null = false
    type = jsonb
  }
  column "target_object" {
    null = false
    type = text
  }
  column "variable_mapping" {
    null = false
    type = jsonb
  }
  column "sampling" {
    null = false
    type = numeric(65,30)
  }
  column "delay" {
    null = false
    type = integer
  }
  column "status" {
    null    = false
    type    = enum.JobConfigState
    default = "ACTIVE"
  }
  column "time_scope" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY['NEW'::text]")
  }
  column "blocked_at" {
    null = true
    type = timestamp(3)
  }
  column "block_reason" {
    null = true
    type = enum.EvaluatorBlockReason
  }
  column "block_message" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "job_configurations_eval_template_id_fkey" {
    columns     = [column.eval_template_id]
    ref_columns = [table.eval_templates.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "job_configurations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "job_configurations_project_id_id_idx" {
    columns = [column.project_id, column.id]
  }
}
table "job_executions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "job_configuration_id" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = enum.JobExecutionStatus
  }
  column "start_time" {
    null = true
    type = timestamp(3)
  }
  column "end_time" {
    null = true
    type = timestamp(3)
  }
  column "error" {
    null = true
    type = text
  }
  column "job_input_trace_id" {
    null = true
    type = text
  }
  column "job_output_score_id" {
    null = true
    type = text
  }
  column "job_input_dataset_item_id" {
    null = true
    type = text
  }
  column "job_input_observation_id" {
    null = true
    type = text
  }
  column "job_template_id" {
    null = true
    type = text
  }
  column "job_input_trace_timestamp" {
    null = true
    type = timestamp(3)
  }
  column "execution_trace_id" {
    null = true
    type = text
  }
  column "job_input_dataset_item_valid_from" {
    null = true
    type = timestamp(3)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "job_executions_job_configuration_id_fkey" {
    columns     = [column.job_configuration_id]
    ref_columns = [table.job_configurations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "job_executions_job_template_id_fkey" {
    columns     = [column.job_template_id]
    ref_columns = [table.eval_templates.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "job_executions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "job_executions_project_id_job_configuration_id_job_input_tr_idx" {
    columns = [column.project_id, column.job_configuration_id, column.job_input_trace_id]
  }
  index "job_executions_project_id_job_output_score_id_idx" {
    columns = [column.project_id, column.job_output_score_id]
  }
}
table "llm_api_keys" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "provider" {
    null = false
    type = text
  }
  column "display_secret_key" {
    null = false
    type = text
  }
  column "secret_key" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "base_url" {
    null = true
    type = text
  }
  column "adapter" {
    null = false
    type = text
  }
  column "custom_models" {
    null    = false
    type    = sql("text[]")
    default = "{}"
  }
  column "with_default_models" {
    null    = false
    type    = boolean
    default = true
  }
  column "config" {
    null = true
    type = jsonb
  }
  column "extra_headers" {
    null = true
    type = text
  }
  column "extra_header_keys" {
    null    = false
    type    = sql("text[]")
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "llm_api_keys_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "llm_api_keys_id_key" {
    unique  = true
    columns = [column.id]
  }
  index "llm_api_keys_project_id_provider_key" {
    unique  = true
    columns = [column.project_id, column.provider]
  }
}
table "llm_schemas" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "schema" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "llm_schemas_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "llm_schemas_project_id_name_key" {
    unique  = true
    columns = [column.project_id, column.name]
  }
}
table "llm_tools" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "parameters" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "llm_tools_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "llm_tools_project_id_name_key" {
    unique  = true
    columns = [column.project_id, column.name]
  }
}
table "media" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "sha_256_hash" {
    null = false
    type = character(44)
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "uploaded_at" {
    null = true
    type = timestamp(3)
  }
  column "upload_http_status" {
    null = true
    type = integer
  }
  column "upload_http_error" {
    null = true
    type = text
  }
  column "bucket_path" {
    null = false
    type = text
  }
  column "bucket_name" {
    null = false
    type = text
  }
  column "content_type" {
    null = false
    type = text
  }
  column "content_length" {
    null = false
    type = bigint
  }
  foreign_key "media_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "media_project_id_created_at_idx" {
    columns = [column.project_id, column.created_at]
  }
  index "media_project_id_id_key" {
    unique  = true
    columns = [column.project_id, column.id]
  }
  index "media_project_id_sha_256_hash_key" {
    unique  = true
    columns = [column.project_id, column.sha_256_hash]
  }
}
table "membership_invitations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "email" {
    null = false
    type = text
  }
  column "project_id" {
    null = true
    type = text
  }
  column "invited_by_user_id" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "org_id" {
    null = false
    type = text
  }
  column "org_role" {
    null = false
    type = enum.Role
  }
  column "project_role" {
    null = true
    type = enum.Role
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "membership_invitations_invited_by_user_id_fkey" {
    columns     = [column.invited_by_user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "membership_invitations_org_id_fkey" {
    columns     = [column.org_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "membership_invitations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  index "membership_invitations_email_idx" {
    columns = [column.email]
  }
  index "membership_invitations_email_org_id_key" {
    unique  = true
    columns = [column.email, column.org_id]
  }
  index "membership_invitations_id_key" {
    unique  = true
    columns = [column.id]
  }
  index "membership_invitations_org_id_idx" {
    columns = [column.org_id]
  }
  index "membership_invitations_project_id_idx" {
    columns = [column.project_id]
  }
}
table "mixpanel_integrations" {
  schema = schema.public
  column "project_id" {
    null = false
    type = text
  }
  column "encrypted_mixpanel_project_token" {
    null = false
    type = text
  }
  column "mixpanel_region" {
    null = false
    type = text
  }
  column "last_sync_at" {
    null = true
    type = timestamp(3)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "export_source" {
    null    = false
    type    = enum.AnalyticsIntegrationExportSource
    default = "TRACES_OBSERVATIONS"
  }
  primary_key {
    columns = [column.project_id]
  }
  foreign_key "mixpanel_integrations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "models" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = true
    type = text
  }
  column "model_name" {
    null = false
    type = text
  }
  column "match_pattern" {
    null = false
    type = text
  }
  column "start_date" {
    null = true
    type = timestamp(3)
  }
  column "input_price" {
    null = true
    type = numeric(65,30)
  }
  column "output_price" {
    null = true
    type = numeric(65,30)
  }
  column "total_price" {
    null = true
    type = numeric(65,30)
  }
  column "unit" {
    null = true
    type = text
  }
  column "tokenizer_config" {
    null = true
    type = jsonb
  }
  column "tokenizer_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "models_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "models_model_name_idx" {
    columns = [column.model_name]
  }
  index "models_project_id_model_name_start_date_unit_key" {
    unique  = true
    columns = [column.project_id, column.model_name, column.start_date, column.unit]
  }
}
table "notification_preferences" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "channel" {
    null = false
    type = enum.NotificationChannel
  }
  column "type" {
    null = false
    type = enum.NotificationType
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "notification_preferences_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "notification_preferences_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "notification_preferences_user_id_project_id_channel_type_key" {
    unique  = true
    columns = [column.user_id, column.project_id, column.channel, column.type]
  }
}
table "observation_media" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "media_id" {
    null = false
    type = text
  }
  column "trace_id" {
    null = false
    type = text
  }
  column "observation_id" {
    null = false
    type = text
  }
  column "field" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "observation_media_media_id_project_id_fkey" {
    columns     = [column.media_id, column.project_id]
    ref_columns = [table.media.column.id, table.media.column.project_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "observation_media_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "observation_media_project_id_media_id_idx" {
    columns = [column.project_id, column.media_id]
  }
  index "observation_media_project_id_trace_id_observation_id_media__key" {
    unique  = true
    columns = [column.project_id, column.trace_id, column.observation_id, column.media_id, column.field]
  }
}
table "observations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = true
    type = text
  }
  column "start_time" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "end_time" {
    null = true
    type = timestamp(3)
  }
  column "parent_observation_id" {
    null = true
    type = text
  }
  column "type" {
    null = false
    type = enum.ObservationType
  }
  column "trace_id" {
    null = true
    type = text
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "model" {
    null = true
    type = text
  }
  column "modelParameters" {
    null = true
    type = jsonb
  }
  column "input" {
    null = true
    type = jsonb
  }
  column "output" {
    null = true
    type = jsonb
  }
  column "level" {
    null    = false
    type    = enum.ObservationLevel
    default = "DEFAULT"
  }
  column "status_message" {
    null = true
    type = text
  }
  column "completion_start_time" {
    null = true
    type = timestamp(3)
  }
  column "completion_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "prompt_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "total_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "version" {
    null = true
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "unit" {
    null = true
    type = text
  }
  column "prompt_id" {
    null = true
    type = text
  }
  column "input_cost" {
    null = true
    type = numeric(65,30)
  }
  column "output_cost" {
    null = true
    type = numeric(65,30)
  }
  column "total_cost" {
    null = true
    type = numeric(65,30)
  }
  column "internal_model" {
    null = true
    type = text
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "calculated_input_cost" {
    null = true
    type = numeric(65,30)
  }
  column "calculated_output_cost" {
    null = true
    type = numeric(65,30)
  }
  column "calculated_total_cost" {
    null = true
    type = numeric(65,30)
  }
  column "internal_model_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "observations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "observations_created_at_idx" {
    columns = [column.created_at]
  }
  index "observations_id_project_id_key" {
    unique  = true
    columns = [column.id, column.project_id]
  }
  index "observations_internal_model_idx" {
    columns = [column.internal_model]
  }
  index "observations_model_idx" {
    columns = [column.model]
  }
  index "observations_project_id_internal_model_start_time_unit_idx" {
    columns = [column.project_id, column.internal_model, column.start_time, column.unit]
  }
  index "observations_project_id_prompt_id_idx" {
    columns = [column.project_id, column.prompt_id]
  }
  index "observations_project_id_start_time_type_idx" {
    columns = [column.project_id, column.start_time, column.type]
  }
  index "observations_prompt_id_idx" {
    columns = [column.prompt_id]
  }
  index "observations_start_time_idx" {
    columns = [column.start_time]
  }
  index "observations_trace_id_project_id_start_time_idx" {
    columns = [column.trace_id, column.project_id, column.start_time]
  }
  index "observations_trace_id_project_id_type_start_time_idx" {
    columns = [column.trace_id, column.project_id, column.type, column.start_time]
  }
  index "observations_type_idx" {
    columns = [column.type]
  }
}
table "organization_memberships" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "org_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "role" {
    null = false
    type = enum.Role
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organization_memberships_org_id_fkey" {
    columns     = [column.org_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "organization_memberships_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "organization_memberships_org_id_user_id_key" {
    unique  = true
    columns = [column.org_id, column.user_id]
  }
  index "organization_memberships_user_id_idx" {
    columns = [column.user_id]
  }
}
table "organizations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "cloud_config" {
    null = true
    type = jsonb
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "ai_features_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "cloud_billing_cycle_anchor" {
    null    = true
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "cloud_billing_cycle_updated_at" {
    null = true
    type = timestamp(3)
  }
  column "cloud_current_cycle_usage" {
    null = true
    type = integer
  }
  column "cloud_free_tier_usage_threshold_state" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "pending_deletions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "object" {
    null = false
    type = text
  }
  column "object_id" {
    null = false
    type = text
  }
  column "is_deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "pending_deletions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "pending_deletions_object_id_object_idx" {
    columns = [column.object_id, column.object]
  }
  index "pending_deletions_project_id_object_is_deleted_object_id_id_idx" {
    columns = [column.project_id, column.object, column.is_deleted, column.object_id, column.id]
  }
}
table "posthog_integrations" {
  schema = schema.public
  column "project_id" {
    null = false
    type = text
  }
  column "encrypted_posthog_api_key" {
    null = false
    type = text
  }
  column "posthog_host_name" {
    null = false
    type = text
  }
  column "last_sync_at" {
    null = true
    type = timestamp(3)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "export_source" {
    null    = false
    type    = enum.AnalyticsIntegrationExportSource
    default = "TRACES_OBSERVATIONS"
  }
  primary_key {
    columns = [column.project_id]
  }
  foreign_key "posthog_integrations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "prices" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "model_id" {
    null = false
    type = text
  }
  column "usage_type" {
    null = false
    type = text
  }
  column "price" {
    null = false
    type = numeric(65,30)
  }
  column "project_id" {
    null = true
    type = text
  }
  column "pricing_tier_id" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "prices_model_id_fkey" {
    columns     = [column.model_id]
    ref_columns = [table.models.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "prices_pricing_tier_id_fkey" {
    columns     = [column.pricing_tier_id]
    ref_columns = [table.pricing_tiers.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "prices_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "prices_model_id_usage_type_pricing_tier_id_key" {
    unique  = true
    columns = [column.model_id, column.usage_type, column.pricing_tier_id]
  }
  index "prices_pricing_tier_id_idx" {
    columns = [column.pricing_tier_id]
  }
}
table "pricing_tiers" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "model_id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "is_default" {
    null    = false
    type    = boolean
    default = false
  }
  column "priority" {
    null = false
    type = integer
  }
  column "conditions" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "pricing_tiers_model_id_fkey" {
    columns     = [column.model_id]
    ref_columns = [table.models.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "pricing_tiers_model_id_name_key" {
    unique  = true
    columns = [column.model_id, column.name]
  }
  index "pricing_tiers_model_id_priority_key" {
    unique  = true
    columns = [column.model_id, column.priority]
  }
}
table "project_memberships" {
  schema = schema.public
  column "project_id" {
    null = false
    type = text
  }
  column "user_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "org_membership_id" {
    null = false
    type = text
  }
  column "role" {
    null = false
    type = enum.Role
  }
  primary_key {
    columns = [column.project_id, column.user_id]
  }
  foreign_key "project_memberships_org_membership_id_fkey" {
    columns     = [column.org_membership_id]
    ref_columns = [table.organization_memberships.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "project_memberships_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "project_memberships_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "project_memberships_org_membership_id_idx" {
    columns = [column.org_membership_id]
  }
  index "project_memberships_project_id_idx" {
    columns = [column.project_id]
  }
  index "project_memberships_user_id_idx" {
    columns = [column.user_id]
  }
}
table "projects" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "name" {
    null = false
    type = text
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "org_id" {
    null = false
    type = text
  }
  column "deleted_at" {
    null = true
    type = timestamp(3)
  }
  column "retention_days" {
    null = true
    type = integer
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "has_traces" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_org_id_fkey" {
    columns     = [column.org_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "projects_org_id_idx" {
    columns = [column.org_id]
  }
}
table "prompt_dependencies" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "parent_id" {
    null = false
    type = text
  }
  column "child_name" {
    null = false
    type = text
  }
  column "child_label" {
    null = true
    type = text
  }
  column "child_version" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "prompt_dependencies_parent_id_fkey" {
    columns     = [column.parent_id]
    ref_columns = [table.prompts.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "prompt_dependencies_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "prompt_dependencies_project_id_child_name" {
    columns = [column.project_id, column.child_name]
  }
  index "prompt_dependencies_project_id_parent_id" {
    columns = [column.project_id, column.parent_id]
  }
}
table "prompt_protected_labels" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "label" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "prompt_protected_labels_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "prompt_protected_labels_project_id_label_key" {
    unique  = true
    columns = [column.project_id, column.label]
  }
}
table "prompts" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_by" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = integer
  }
  column "is_active" {
    null = true
    type = boolean
  }
  column "config" {
    null    = false
    type    = json
    default = "{}"
  }
  column "prompt" {
    null = false
    type = jsonb
  }
  column "type" {
    null    = false
    type    = text
    default = "text"
  }
  column "tags" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "labels" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "commit_message" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "prompts_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "prompts_created_at_idx" {
    columns = [column.created_at]
  }
  index "prompts_project_id_id_idx" {
    columns = [column.project_id, column.id]
  }
  index "prompts_project_id_name_version_key" {
    unique  = true
    columns = [column.project_id, column.name, column.version]
  }
  index "prompts_tags_idx" {
    columns = [column.tags]
    type    = GIN
  }
  index "prompts_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "score_configs" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "data_type" {
    null = false
    type = enum.ScoreConfigDataType
  }
  column "is_archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "min_value" {
    null = true
    type = double_precision
  }
  column "max_value" {
    null = true
    type = double_precision
  }
  column "categories" {
    null = true
    type = jsonb
  }
  column "description" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "score_configs_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "score_configs_categories_idx" {
    columns = [column.categories]
  }
  index "score_configs_created_at_idx" {
    columns = [column.created_at]
  }
  index "score_configs_data_type_idx" {
    columns = [column.data_type]
  }
  index "score_configs_id_project_id_key" {
    unique  = true
    columns = [column.id, column.project_id]
  }
  index "score_configs_is_archived_idx" {
    columns = [column.is_archived]
  }
  index "score_configs_project_id_idx" {
    columns = [column.project_id]
  }
  index "score_configs_updated_at_idx" {
    columns = [column.updated_at]
  }
}
table "scores" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "timestamp" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "name" {
    null = false
    type = text
  }
  column "value" {
    null = true
    type = double_precision
  }
  column "observation_id" {
    null = true
    type = text
  }
  column "trace_id" {
    null = false
    type = text
  }
  column "comment" {
    null = true
    type = text
  }
  column "source" {
    null = false
    type = enum.ScoreSource
  }
  column "project_id" {
    null = false
    type = text
  }
  column "author_user_id" {
    null = true
    type = text
  }
  column "config_id" {
    null = true
    type = text
  }
  column "data_type" {
    null    = false
    type    = enum.ScoreConfigDataType
    default = "NUMERIC"
  }
  column "string_value" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "queue_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "scores_config_id_fkey" {
    columns     = [column.config_id]
    ref_columns = [table.score_configs.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "scores_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "scores_author_user_id_idx" {
    columns = [column.author_user_id]
  }
  index "scores_config_id_idx" {
    columns = [column.config_id]
  }
  index "scores_created_at_idx" {
    columns = [column.created_at]
  }
  index "scores_id_project_id_key" {
    unique  = true
    columns = [column.id, column.project_id]
  }
  index "scores_observation_id_idx" {
    columns = [column.observation_id]
    type    = HASH
  }
  index "scores_project_id_name_idx" {
    columns = [column.project_id, column.name]
  }
  index "scores_source_idx" {
    columns = [column.source]
  }
  index "scores_timestamp_idx" {
    columns = [column.timestamp]
  }
  index "scores_trace_id_idx" {
    columns = [column.trace_id]
    type    = HASH
  }
  index "scores_value_idx" {
    columns = [column.value]
  }
}
table "slack_integrations" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "team_id" {
    null = false
    type = text
  }
  column "team_name" {
    null = false
    type = text
  }
  column "bot_token" {
    null = false
    type = text
  }
  column "bot_user_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "slack_integrations_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "slack_integrations_project_id_key" {
    unique  = true
    columns = [column.project_id]
  }
  index "slack_integrations_team_id_idx" {
    columns = [column.team_id]
  }
}
table "sso_configs" {
  schema = schema.public
  column "domain" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "auth_provider" {
    null = false
    type = text
  }
  column "auth_config" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.domain]
  }
}
table "surveys" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "survey_name" {
    null = false
    type = enum.SurveyName
  }
  column "response" {
    null = false
    type = jsonb
  }
  column "user_id" {
    null = true
    type = text
  }
  column "user_email" {
    null = true
    type = text
  }
  column "org_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "surveys_org_id_fkey" {
    columns     = [column.org_id]
    ref_columns = [table.organizations.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "surveys_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "table_view_presets" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "table_name" {
    null = false
    type = text
  }
  column "created_by" {
    null = true
    type = text
  }
  column "updated_by" {
    null = true
    type = text
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "column_order" {
    null = false
    type = jsonb
  }
  column "column_visibility" {
    null = false
    type = jsonb
  }
  column "search_query" {
    null = true
    type = text
  }
  column "order_by" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "table_view_presets_created_by_fkey" {
    columns     = [column.created_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  foreign_key "table_view_presets_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "table_view_presets_updated_by_fkey" {
    columns     = [column.updated_by]
    ref_columns = [table.users.column.id]
    on_update   = CASCADE
    on_delete   = SET_NULL
  }
  index "table_view_presets_project_id_table_name_name_key" {
    unique  = true
    columns = [column.project_id, column.table_name, column.name]
  }
}
table "trace_media" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "media_id" {
    null = false
    type = text
  }
  column "trace_id" {
    null = false
    type = text
  }
  column "field" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "trace_media_media_id_project_id_fkey" {
    columns     = [column.media_id, column.project_id]
    ref_columns = [table.media.column.id, table.media.column.project_id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "trace_media_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "trace_media_project_id_media_id_idx" {
    columns = [column.project_id, column.media_id]
  }
  index "trace_media_project_id_trace_id_media_id_field_key" {
    unique  = true
    columns = [column.project_id, column.trace_id, column.media_id, column.field]
  }
}
table "trace_sessions" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "bookmarked" {
    null    = false
    type    = boolean
    default = false
  }
  column "public" {
    null    = false
    type    = boolean
    default = false
  }
  column "environment" {
    null    = false
    type    = text
    default = "default"
  }
  primary_key {
    columns = [column.id, column.project_id]
  }
  foreign_key "trace_sessions_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "trace_sessions_project_id_created_at_idx" {
    on {
      column = column.project_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
}
table "traces" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "timestamp" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "name" {
    null = true
    type = text
  }
  column "project_id" {
    null = false
    type = text
  }
  column "metadata" {
    null = true
    type = jsonb
  }
  column "external_id" {
    null = true
    type = text
  }
  column "user_id" {
    null = true
    type = text
  }
  column "release" {
    null = true
    type = text
  }
  column "version" {
    null = true
    type = text
  }
  column "public" {
    null    = false
    type    = boolean
    default = false
  }
  column "bookmarked" {
    null    = false
    type    = boolean
    default = false
  }
  column "input" {
    null = true
    type = jsonb
  }
  column "output" {
    null = true
    type = jsonb
  }
  column "session_id" {
    null = true
    type = text
  }
  column "tags" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "traces_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "traces_created_at_idx" {
    columns = [column.created_at]
  }
  index "traces_id_user_id_idx" {
    columns = [column.id, column.user_id]
  }
  index "traces_name_idx" {
    columns = [column.name]
  }
  index "traces_project_id_timestamp_idx" {
    columns = [column.project_id, column.timestamp]
  }
  index "traces_session_id_idx" {
    columns = [column.session_id]
  }
  index "traces_tags_idx" {
    columns = [column.tags]
    type    = GIN
  }
  index "traces_timestamp_idx" {
    columns = [column.timestamp]
  }
  index "traces_user_id_idx" {
    columns = [column.user_id]
  }
}
table "triggers" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "project_id" {
    null = false
    type = text
  }
  column "eventSource" {
    null = false
    type = text
  }
  column "eventActions" {
    null = true
    type = sql("text[]")
  }
  column "filter" {
    null = true
    type = jsonb
  }
  column "status" {
    null    = false
    type    = enum.JobConfigState
    default = "ACTIVE"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "triggers_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "triggers_project_id_idx" {
    columns = [column.project_id]
  }
}
table "users" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = true
    type = text
  }
  column "email" {
    null = true
    type = text
  }
  column "email_verified" {
    null = true
    type = timestamp(3)
  }
  column "password" {
    null = true
    type = text
  }
  column "image" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "feature_flags" {
    null    = true
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  column "admin" {
    null    = false
    type    = boolean
    default = false
  }
  column "v4_beta_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "users_email_key" {
    unique  = true
    columns = [column.email]
  }
}
table "verification_tokens" {
  schema = schema.public
  column "identifier" {
    null = false
    type = text
  }
  column "token" {
    null = false
    type = text
  }
  column "expires" {
    null = false
    type = timestamp(3)
  }
  index "verification_tokens_identifier_token_key" {
    unique  = true
    columns = [column.identifier, column.token]
  }
  index "verification_tokens_token_key" {
    unique  = true
    columns = [column.token]
  }
}
enum "ObservationType" {
  schema = schema.public
  values = ["SPAN", "EVENT", "GENERATION", "AGENT", "TOOL", "CHAIN", "RETRIEVER", "EVALUATOR", "EMBEDDING", "GUARDRAIL"]
}
enum "ObservationLevel" {
  schema = schema.public
  values = ["DEBUG", "DEFAULT", "WARNING", "ERROR"]
}
enum "DatasetStatus" {
  schema = schema.public
  values = ["ACTIVE", "ARCHIVED"]
}
enum "JobType" {
  schema = schema.public
  values = ["EVAL"]
}
enum "JobExecutionStatus" {
  schema = schema.public
  values = ["COMPLETED", "ERROR", "PENDING", "CANCELLED", "DELAYED"]
}
enum "JobConfigState" {
  schema = schema.public
  values = ["ACTIVE", "INACTIVE"]
}
enum "ScoreConfigDataType" {
  schema = schema.public
  values = ["CATEGORICAL", "NUMERIC", "BOOLEAN"]
}
enum "ScoreSource" {
  schema = schema.public
  values = ["ANNOTATION", "API", "EVAL"]
}
enum "Role" {
  schema = schema.public
  values = ["OWNER", "ADMIN", "MEMBER", "VIEWER", "NONE"]
}
enum "CommentObjectType" {
  schema = schema.public
  values = ["TRACE", "OBSERVATION", "SESSION", "PROMPT"]
}
enum "AnnotationQueueStatus" {
  schema = schema.public
  values = ["PENDING", "COMPLETED"]
}
enum "AnnotationQueueObjectType" {
  schema = schema.public
  values = ["TRACE", "OBSERVATION", "SESSION"]
}
enum "AuditLogRecordType" {
  schema = schema.public
  values = ["USER", "API_KEY"]
}
enum "BlobStorageIntegrationType" {
  schema = schema.public
  values = ["S3", "S3_COMPATIBLE", "AZURE_BLOB_STORAGE"]
}
enum "BlobStorageIntegrationFileType" {
  schema = schema.public
  values = ["JSON", "CSV", "JSONL"]
}
enum "DashboardWidgetViews" {
  schema = schema.public
  values = ["TRACES", "OBSERVATIONS", "SCORES_NUMERIC", "SCORES_CATEGORICAL"]
}
enum "DashboardWidgetChartType" {
  schema = schema.public
  values = ["LINE_TIME_SERIES", "BAR_TIME_SERIES", "HORIZONTAL_BAR", "VERTICAL_BAR", "PIE", "NUMBER", "HISTOGRAM", "PIVOT_TABLE", "AREA_TIME_SERIES"]
}
enum "ApiKeyScope" {
  schema = schema.public
  values = ["ORGANIZATION", "PROJECT"]
}
enum "ActionType" {
  schema = schema.public
  values = ["WEBHOOK", "SLACK", "GITHUB_DISPATCH"]
}
enum "ActionExecutionStatus" {
  schema = schema.public
  values = ["COMPLETED", "ERROR", "PENDING", "CANCELLED"]
}
enum "BlobStorageExportMode" {
  schema = schema.public
  values = ["FULL_HISTORY", "FROM_TODAY", "FROM_CUSTOM_DATE"]
}
enum "SurveyName" {
  schema = schema.public
  values = ["org_onboarding", "user_onboarding"]
}
enum "NotificationChannel" {
  schema = schema.public
  values = ["EMAIL"]
}
enum "NotificationType" {
  schema = schema.public
  values = ["COMMENT_MENTION"]
}
enum "AnalyticsIntegrationExportSource" {
  schema = schema.public
  values = ["TRACES_OBSERVATIONS", "TRACES_OBSERVATIONS_EVENTS", "EVENTS"]
}
enum "EvaluatorBlockReason" {
  schema = schema.public
  values = ["LLM_CONNECTION_AUTH_INVALID", "LLM_CONNECTION_MISSING", "DEFAULT_EVAL_MODEL_MISSING", "EVAL_MODEL_CONFIG_INVALID", "EVAL_MODEL_UNAVAILABLE", "PROVIDER_ACCOUNT_NOT_READY"]
}
schema "public" {
  comment = "standard public schema"
}
