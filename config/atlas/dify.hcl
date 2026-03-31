Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "account_integrates" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(16)
  }
  column "open_id" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_token" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_account_provider" {
    columns = [column.account_id, column.provider]
  }
  unique "unique_provider_open_id" {
    columns = [column.provider, column.open_id]
  }
}
table "account_plugin_permissions" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "install_permission" {
    null    = false
    type    = character_varying(16)
    default = "everyone"
  }
  column "debug_permission" {
    null    = false
    type    = character_varying(16)
    default = "noone"
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_tenant_plugin" {
    columns = [column.tenant_id]
  }
}
table "account_trial_app_records" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "count" {
    null = false
    type = integer
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "account_trial_app_record_account_id_idx" {
    columns = [column.account_id]
  }
  index "account_trial_app_record_app_id_idx" {
    columns = [column.app_id]
  }
  unique "unique_account_trial_app_record" {
    columns = [column.account_id, column.app_id]
  }
}
table "accounts" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "password" {
    null = true
    type = character_varying(255)
  }
  column "password_salt" {
    null = true
    type = character_varying(255)
  }
  column "avatar" {
    null = true
    type = character_varying(255)
  }
  column "interface_language" {
    null = true
    type = character_varying(255)
  }
  column "interface_theme" {
    null = true
    type = character_varying(255)
  }
  column "timezone" {
    null = true
    type = character_varying(255)
  }
  column "last_login_at" {
    null = true
    type = timestamp
  }
  column "last_login_ip" {
    null = true
    type = character_varying(255)
  }
  column "status" {
    null    = false
    type    = character_varying(16)
    default = "active"
  }
  column "initialized_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "last_active_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "account_email_idx" {
    columns = [column.email]
  }
}
table "agent_strategy_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(127)
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_agent_strategy_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_agent_strategy_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_agent_strategy_installations_provider" {
    columns = [column.provider]
  }
  index "idx_agent_strategy_installations_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "ai_model_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "provider" {
    null = false
    type = character_varying(127)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_ai_model_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_ai_model_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_ai_model_installations_provider" {
    columns = [column.provider]
  }
  index "idx_ai_model_installations_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "alembic_version" {
  schema = schema.public
  column "version_num" {
    null = false
    type = character_varying(32)
  }
  primary_key {
    columns = [column.version_num]
  }
}
table "api_based_extensions" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "api_endpoint" {
    null = false
    type = character_varying(255)
  }
  column "api_key" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "api_based_extension_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "api_requests" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "api_token_id" {
    null = false
    type = uuid
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "request" {
    null = true
    type = text
  }
  column "response" {
    null = true
    type = text
  }
  column "ip" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "api_request_token_idx" {
    columns = [column.tenant_id, column.api_token_id]
  }
}
table "api_tokens" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = true
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(16)
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "last_used_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "api_token_app_id_type_idx" {
    columns = [column.app_id, column.type]
  }
  index "api_token_tenant_idx" {
    columns = [column.tenant_id, column.type]
  }
  index "api_token_token_idx" {
    columns = [column.token, column.type]
  }
}
table "app_annotation_hit_histories" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "annotation_id" {
    null = false
    type = uuid
  }
  column "source" {
    null = false
    type = text
  }
  column "question" {
    null = false
    type = text
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "score" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "annotation_question" {
    null = false
    type = text
  }
  column "annotation_content" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "app_annotation_hit_histories_account_idx" {
    columns = [column.account_id]
  }
  index "app_annotation_hit_histories_annotation_idx" {
    columns = [column.annotation_id]
  }
  index "app_annotation_hit_histories_app_idx" {
    columns = [column.app_id]
  }
  index "app_annotation_hit_histories_message_idx" {
    columns = [column.message_id]
  }
}
table "app_annotation_settings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "score_threshold" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "collection_binding_id" {
    null = false
    type = uuid
  }
  column "created_user_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_user_id" {
    null = false
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "app_annotation_settings_app_idx" {
    columns = [column.app_id]
  }
}
table "app_dataset_joins" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "app_dataset_join_app_dataset_idx" {
    columns = [column.dataset_id, column.app_id]
  }
}
table "app_mcp_servers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = character_varying(255)
  }
  column "server_code" {
    null = false
    type = character_varying(255)
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "normal"
  }
  column "parameters" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_app_mcp_server_server_code" {
    columns = [column.server_code]
  }
  unique "unique_app_mcp_server_tenant_app_id" {
    columns = [column.tenant_id, column.app_id]
  }
}
table "app_model_configs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = true
    type = character_varying(255)
  }
  column "model_id" {
    null = true
    type = character_varying(255)
  }
  column "configs" {
    null = true
    type = json
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "opening_statement" {
    null = true
    type = text
  }
  column "suggested_questions" {
    null = true
    type = text
  }
  column "suggested_questions_after_answer" {
    null = true
    type = text
  }
  column "more_like_this" {
    null = true
    type = text
  }
  column "model" {
    null = true
    type = text
  }
  column "user_input_form" {
    null = true
    type = text
  }
  column "pre_prompt" {
    null = true
    type = text
  }
  column "agent_mode" {
    null = true
    type = text
  }
  column "speech_to_text" {
    null = true
    type = text
  }
  column "sensitive_word_avoidance" {
    null = true
    type = text
  }
  column "retriever_resource" {
    null = true
    type = text
  }
  column "dataset_query_variable" {
    null = true
    type = character_varying(255)
  }
  column "prompt_type" {
    null    = false
    type    = character_varying(255)
    default = "simple"
  }
  column "chat_prompt_config" {
    null = true
    type = text
  }
  column "completion_prompt_config" {
    null = true
    type = text
  }
  column "dataset_configs" {
    null = true
    type = text
  }
  column "external_data_tools" {
    null = true
    type = text
  }
  column "file_upload" {
    null = true
    type = text
  }
  column "text_to_speech" {
    null = true
    type = text
  }
  column "created_by" {
    null = true
    type = uuid
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "app_app_id_idx" {
    columns = [column.app_id]
  }
}
table "app_triggers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "node_id" {
    null = false
    type = character_varying(64)
  }
  column "trigger_type" {
    null = false
    type = character_varying(50)
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "provider_name" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  index "app_trigger_tenant_app_idx" {
    columns = [column.tenant_id, column.app_id]
  }
}
table "apps" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "mode" {
    null = false
    type = character_varying(255)
  }
  column "icon" {
    null = true
    type = character_varying(255)
  }
  column "icon_background" {
    null = true
    type = character_varying(255)
  }
  column "app_model_config_id" {
    null = true
    type = uuid
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "normal"
  }
  column "enable_site" {
    null = false
    type = boolean
  }
  column "enable_api" {
    null = false
    type = boolean
  }
  column "api_rpm" {
    null    = false
    type    = integer
    default = 0
  }
  column "api_rph" {
    null    = false
    type    = integer
    default = 0
  }
  column "is_demo" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_public" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "is_universal" {
    null    = false
    type    = boolean
    default = false
  }
  column "workflow_id" {
    null = true
    type = uuid
  }
  column "description" {
    null    = false
    type    = text
    default = ""
  }
  column "tracing" {
    null = true
    type = text
  }
  column "max_active_requests" {
    null = true
    type = integer
  }
  column "icon_type" {
    null = true
    type = character_varying(255)
  }
  column "created_by" {
    null = true
    type = uuid
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "use_icon_as_answer_icon" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "app_tenant_id_idx" {
    columns = [column.tenant_id]
  }
}
table "celery_taskmeta" {
  schema = schema.public
  column "id" {
    null    = false
    type    = integer
    default = sql("nextval('public.task_id_sequence'::regclass)")
  }
  column "task_id" {
    null = false
    type = character_varying(155)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "result" {
    null = true
    type = bytea
  }
  column "date_done" {
    null = true
    type = timestamp
  }
  column "traceback" {
    null = true
    type = text
  }
  column "name" {
    null = true
    type = character_varying(155)
  }
  column "args" {
    null = true
    type = bytea
  }
  column "kwargs" {
    null = true
    type = bytea
  }
  column "worker" {
    null = true
    type = character_varying(155)
  }
  column "retries" {
    null = true
    type = integer
  }
  column "queue" {
    null = true
    type = character_varying(155)
  }
  primary_key {
    columns = [column.id]
  }
  unique "celery_taskmeta_task_id_key" {
    columns = [column.task_id]
  }
}
table "celery_tasksetmeta" {
  schema = schema.public
  column "id" {
    null    = false
    type    = integer
    default = sql("nextval('public.taskset_id_sequence'::regclass)")
  }
  column "taskset_id" {
    null = false
    type = character_varying(155)
  }
  column "result" {
    null = true
    type = bytea
  }
  column "date_done" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  unique "celery_tasksetmeta_taskset_id_key" {
    columns = [column.taskset_id]
  }
}
table "child_chunks" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "segment_id" {
    null = false
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "content" {
    null = false
    type = text
  }
  column "word_count" {
    null = false
    type = integer
  }
  column "index_node_id" {
    null = true
    type = character_varying(255)
  }
  column "index_node_hash" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null    = false
    type    = character_varying(255)
    default = "automatic"
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "indexing_at" {
    null = true
    type = timestamp
  }
  column "completed_at" {
    null = true
    type = timestamp
  }
  column "error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "child_chunk_dataset_id_idx" {
    columns = [column.tenant_id, column.dataset_id, column.document_id, column.segment_id, column.index_node_id]
  }
  index "child_chunks_node_idx" {
    columns = [column.index_node_id, column.dataset_id]
  }
  index "child_chunks_segment_idx" {
    columns = [column.segment_id]
  }
}
table "conversations" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "app_model_config_id" {
    null = true
    type = uuid
  }
  column "model_provider" {
    null = true
    type = character_varying(255)
  }
  column "override_model_configs" {
    null = true
    type = text
  }
  column "model_id" {
    null = true
    type = character_varying(255)
  }
  column "mode" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "summary" {
    null = true
    type = text
  }
  column "inputs" {
    null = false
    type = json
  }
  column "introduction" {
    null = true
    type = text
  }
  column "system_instruction" {
    null = true
    type = text
  }
  column "system_instruction_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "from_source" {
    null = false
    type = character_varying(255)
  }
  column "from_end_user_id" {
    null = true
    type = uuid
  }
  column "from_account_id" {
    null = true
    type = uuid
  }
  column "read_at" {
    null = true
    type = timestamp
  }
  column "read_account_id" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "is_deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "invoke_from" {
    null = true
    type = character_varying(255)
  }
  column "dialogue_count" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "conversation_app_created_at_idx" {
    where = "(is_deleted IS FALSE)"
    on {
      column = column.app_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
  index "conversation_app_from_user_idx" {
    columns = [column.app_id, column.from_source, column.from_end_user_id]
  }
  index "conversation_app_updated_at_idx" {
    where = "(is_deleted IS FALSE)"
    on {
      column = column.app_id
    }
    on {
      desc   = true
      column = column.updated_at
    }
  }
}
table "data_source_api_key_auth_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "category" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "credentials" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "disabled" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "data_source_api_key_auth_binding_provider_idx" {
    columns = [column.provider]
  }
  index "data_source_api_key_auth_binding_tenant_id_idx" {
    columns = [column.tenant_id]
  }
}
table "data_source_oauth_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "access_token" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "source_info" {
    null = false
    type = jsonb
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "disabled" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "source_binding_tenant_id_idx" {
    columns = [column.tenant_id]
  }
  index "source_info_idx" {
    columns = [column.source_info]
    type    = GIN
  }
}
table "dataset_auto_disable_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "notified" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_auto_disable_log_created_atx" {
    columns = [column.created_at]
  }
  index "dataset_auto_disable_log_dataset_idx" {
    columns = [column.dataset_id]
  }
  index "dataset_auto_disable_log_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "dataset_collection_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "collection_name" {
    null = false
    type = character_varying(64)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "type" {
    null    = false
    type    = character_varying(40)
    default = "dataset"
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_model_name_idx" {
    columns = [column.provider_name, column.model_name]
  }
}
table "dataset_keyword_tables" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "keyword_table" {
    null = false
    type = text
  }
  column "data_source_type" {
    null    = false
    type    = character_varying(255)
    default = "database"
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_keyword_table_dataset_id_idx" {
    columns = [column.dataset_id]
  }
  unique "dataset_keyword_tables_dataset_id_key" {
    columns = [column.dataset_id]
  }
}
table "dataset_metadata_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "metadata_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "created_by" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_metadata_binding_dataset_idx" {
    columns = [column.dataset_id]
  }
  index "dataset_metadata_binding_document_idx" {
    columns = [column.document_id]
  }
  index "dataset_metadata_binding_metadata_idx" {
    columns = [column.metadata_id]
  }
  index "dataset_metadata_binding_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "dataset_metadatas" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_metadata_dataset_idx" {
    columns = [column.dataset_id]
  }
  index "dataset_metadata_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "dataset_permissions" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "has_permission" {
    null    = false
    type    = boolean
    default = true
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_dataset_permissions_account_id" {
    columns = [column.account_id]
  }
  index "idx_dataset_permissions_dataset_id" {
    columns = [column.dataset_id]
  }
  index "idx_dataset_permissions_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "dataset_process_rules" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "mode" {
    null    = false
    type    = character_varying(255)
    default = "automatic"
  }
  column "rules" {
    null = true
    type = text
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_process_rule_dataset_id_idx" {
    columns = [column.dataset_id]
  }
}
table "dataset_queries" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "content" {
    null = false
    type = text
  }
  column "source" {
    null = false
    type = character_varying(255)
  }
  column "source_app_id" {
    null = true
    type = uuid
  }
  column "created_by_role" {
    null = false
    type = character_varying
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_query_dataset_id_idx" {
    columns = [column.dataset_id]
  }
}
table "dataset_retriever_resources" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "dataset_name" {
    null = false
    type = text
  }
  column "document_id" {
    null = true
    type = uuid
  }
  column "document_name" {
    null = false
    type = text
  }
  column "data_source_type" {
    null = true
    type = text
  }
  column "segment_id" {
    null = true
    type = uuid
  }
  column "score" {
    null = true
    type = double_precision
  }
  column "content" {
    null = false
    type = text
  }
  column "hit_count" {
    null = true
    type = integer
  }
  column "word_count" {
    null = true
    type = integer
  }
  column "segment_position" {
    null = true
    type = integer
  }
  column "index_node_hash" {
    null = true
    type = text
  }
  column "retriever_from" {
    null = false
    type = text
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_retriever_resource_message_id_idx" {
    columns = [column.message_id]
  }
}
table "datasets" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = text
  }
  column "provider" {
    null    = false
    type    = character_varying(255)
    default = "vendor"
  }
  column "permission" {
    null    = false
    type    = character_varying(255)
    default = "only_me"
  }
  column "data_source_type" {
    null = true
    type = character_varying(255)
  }
  column "indexing_technique" {
    null = true
    type = character_varying(255)
  }
  column "index_struct" {
    null = true
    type = text
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "embedding_model" {
    null    = true
    type    = character_varying(255)
    default = "text-embedding-ada-002"
  }
  column "embedding_model_provider" {
    null    = true
    type    = character_varying(255)
    default = "openai"
  }
  column "collection_binding_id" {
    null = true
    type = uuid
  }
  column "retrieval_model" {
    null = true
    type = jsonb
  }
  column "built_in_field_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "keyword_number" {
    null    = true
    type    = integer
    default = 10
  }
  column "icon_info" {
    null = true
    type = jsonb
  }
  column "runtime_mode" {
    null    = true
    type    = character_varying(255)
    default = "general"
  }
  column "pipeline_id" {
    null = true
    type = uuid
  }
  column "chunk_structure" {
    null = true
    type = character_varying(255)
  }
  column "enable_api" {
    null    = false
    type    = boolean
    default = true
  }
  column "is_multimodal" {
    null    = false
    type    = boolean
    default = false
  }
  column "summary_index_setting" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "dataset_tenant_idx" {
    columns = [column.tenant_id]
  }
  index "retrieval_model_idx" {
    columns = [column.retrieval_model]
    type    = GIN
  }
}
table "datasource_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(127)
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_datasource_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_datasource_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_datasource_installations_provider" {
    columns = [column.provider]
  }
  index "idx_datasource_installations_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "datasource_oauth_params" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "system_credentials" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  unique "datasource_oauth_config_datasource_id_provider_idx" {
    columns = [column.plugin_id, column.provider]
  }
}
table "datasource_oauth_tenant_params" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "client_params" {
    null = false
    type = jsonb
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "datasource_oauth_tenant_config_unique" {
    columns = [column.tenant_id, column.plugin_id, column.provider]
  }
}
table "datasource_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(128)
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "auth_type" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_credentials" {
    null = false
    type = jsonb
  }
  column "avatar_url" {
    null = true
    type = text
  }
  column "is_default" {
    null    = false
    type    = boolean
    default = false
  }
  column "expires_at" {
    null    = false
    type    = integer
    default = -1
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "datasource_provider_auth_type_provider_idx" {
    columns = [column.tenant_id, column.plugin_id, column.provider]
  }
  unique "datasource_provider_unique_name" {
    columns = [column.tenant_id, column.plugin_id, column.provider, column.name]
  }
}
table "dify_setups" {
  schema = schema.public
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "setup_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.version]
  }
}
table "document_pipeline_execution_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "pipeline_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "datasource_type" {
    null = false
    type = character_varying(255)
  }
  column "datasource_info" {
    null = false
    type = text
  }
  column "datasource_node_id" {
    null = false
    type = character_varying(255)
  }
  column "input_data" {
    null = false
    type = json
  }
  column "created_by" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "document_pipeline_execution_logs_document_id_idx" {
    columns = [column.document_id]
  }
}
table "document_segment_summaries" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "chunk_id" {
    null = false
    type = uuid
  }
  column "summary_content" {
    null = true
    type = text
  }
  column "summary_index_node_id" {
    null = true
    type = character_varying(255)
  }
  column "summary_index_node_hash" {
    null = true
    type = character_varying(255)
  }
  column "tokens" {
    null = true
    type = integer
  }
  column "status" {
    null    = false
    type    = character_varying(32)
    default = "generating"
  }
  column "error" {
    null = true
    type = text
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "disabled_at" {
    null = true
    type = timestamp
  }
  column "disabled_by" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "document_segment_summaries_chunk_id_idx" {
    columns = [column.chunk_id]
  }
  index "document_segment_summaries_dataset_id_idx" {
    columns = [column.dataset_id]
  }
  index "document_segment_summaries_document_id_idx" {
    columns = [column.document_id]
  }
  index "document_segment_summaries_status_idx" {
    columns = [column.status]
  }
}
table "document_segments" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "content" {
    null = false
    type = text
  }
  column "word_count" {
    null = false
    type = integer
  }
  column "tokens" {
    null = false
    type = integer
  }
  column "keywords" {
    null = true
    type = json
  }
  column "index_node_id" {
    null = true
    type = character_varying(255)
  }
  column "index_node_hash" {
    null = true
    type = character_varying(255)
  }
  column "hit_count" {
    null = false
    type = integer
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "disabled_at" {
    null = true
    type = timestamp
  }
  column "disabled_by" {
    null = true
    type = uuid
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "waiting"
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "indexing_at" {
    null = true
    type = timestamp
  }
  column "completed_at" {
    null = true
    type = timestamp
  }
  column "error" {
    null = true
    type = text
  }
  column "stopped_at" {
    null = true
    type = timestamp
  }
  column "answer" {
    null = true
    type = text
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "document_segment_dataset_id_idx" {
    columns = [column.dataset_id]
  }
  index "document_segment_document_id_idx" {
    columns = [column.document_id]
  }
  index "document_segment_node_dataset_idx" {
    columns = [column.index_node_id, column.dataset_id]
  }
  index "document_segment_tenant_dataset_idx" {
    columns = [column.dataset_id, column.tenant_id]
  }
  index "document_segment_tenant_document_idx" {
    columns = [column.document_id, column.tenant_id]
  }
  index "document_segment_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "documents" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "data_source_type" {
    null = false
    type = character_varying(255)
  }
  column "data_source_info" {
    null = true
    type = text
  }
  column "dataset_process_rule_id" {
    null = true
    type = uuid
  }
  column "batch" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "created_from" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_api_request_id" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "processing_started_at" {
    null = true
    type = timestamp
  }
  column "file_id" {
    null = true
    type = text
  }
  column "word_count" {
    null = true
    type = integer
  }
  column "parsing_completed_at" {
    null = true
    type = timestamp
  }
  column "cleaning_completed_at" {
    null = true
    type = timestamp
  }
  column "splitting_completed_at" {
    null = true
    type = timestamp
  }
  column "tokens" {
    null = true
    type = integer
  }
  column "indexing_latency" {
    null = true
    type = double_precision
  }
  column "completed_at" {
    null = true
    type = timestamp
  }
  column "is_paused" {
    null    = true
    type    = boolean
    default = false
  }
  column "paused_by" {
    null = true
    type = uuid
  }
  column "paused_at" {
    null = true
    type = timestamp
  }
  column "error" {
    null = true
    type = text
  }
  column "stopped_at" {
    null = true
    type = timestamp
  }
  column "indexing_status" {
    null    = false
    type    = character_varying(255)
    default = "waiting"
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "disabled_at" {
    null = true
    type = timestamp
  }
  column "disabled_by" {
    null = true
    type = uuid
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "archived_reason" {
    null = true
    type = character_varying(255)
  }
  column "archived_by" {
    null = true
    type = uuid
  }
  column "archived_at" {
    null = true
    type = timestamp
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "doc_type" {
    null = true
    type = character_varying(40)
  }
  column "doc_metadata" {
    null = true
    type = jsonb
  }
  column "doc_form" {
    null    = false
    type    = character_varying(255)
    default = "text_model"
  }
  column "doc_language" {
    null = true
    type = character_varying(255)
  }
  column "need_summary" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "document_dataset_id_idx" {
    columns = [column.dataset_id]
  }
  index "document_is_paused_idx" {
    columns = [column.is_paused]
  }
  index "document_metadata_idx" {
    columns = [column.doc_metadata]
    type    = GIN
  }
  index "document_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "embeddings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "hash" {
    null = false
    type = character_varying(64)
  }
  column "embedding" {
    null = false
    type = bytea
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "model_name" {
    null    = false
    type    = character_varying(255)
    default = "text-embedding-ada-002"
  }
  column "provider_name" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "created_at_idx" {
    columns = [column.created_at]
  }
  unique "embedding_hash_idx" {
    columns = [column.model_name, column.hash, column.provider_name]
  }
}
table "end_users" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = true
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "external_user_id" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "is_anonymous" {
    null    = false
    type    = boolean
    default = true
  }
  column "session_id" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "end_user_session_id_idx" {
    columns = [column.session_id, column.type]
  }
  index "end_user_tenant_session_id_idx" {
    columns = [column.tenant_id, column.session_id, column.type]
  }
}
table "endpoints" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "name" {
    null    = true
    type    = character_varying(127)
    default = "default"
  }
  column "hook_id" {
    null = true
    type = character_varying(127)
  }
  column "tenant_id" {
    null = true
    type = character_varying(64)
  }
  column "user_id" {
    null = true
    type = character_varying(64)
  }
  column "plugin_id" {
    null = true
    type = character_varying(64)
  }
  column "expired_at" {
    null = true
    type = timestamptz
  }
  column "enabled" {
    null = true
    type = boolean
  }
  column "settings" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_endpoints_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_endpoints_tenant_id" {
    columns = [column.tenant_id]
  }
  index "idx_endpoints_user_id" {
    columns = [column.user_id]
  }
  unique "uni_endpoints_hook_id" {
    columns = [column.hook_id]
  }
}
table "execution_extra_contents" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "type" {
    null = false
    type = character_varying(30)
  }
  column "workflow_run_id" {
    null = false
    type = uuid
  }
  column "message_id" {
    null = true
    type = uuid
  }
  column "form_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "execution_extra_contents_message_id_idx" {
    columns = [column.message_id]
  }
  index "execution_extra_contents_workflow_run_id_idx" {
    columns = [column.workflow_run_id]
  }
}
table "exporle_banners" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "content" {
    null = false
    type = json
  }
  column "link" {
    null = false
    type = character_varying(255)
  }
  column "sort" {
    null = false
    type = integer
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "enabled"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "language" {
    null    = false
    type    = character_varying(255)
    default = "en-US"
  }
  primary_key {
    columns = [column.id]
  }
}
table "external_knowledge_apis" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = character_varying(255)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "settings" {
    null = true
    type = text
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "external_knowledge_apis_name_idx" {
    columns = [column.name]
  }
  index "external_knowledge_apis_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "external_knowledge_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "external_knowledge_api_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "external_knowledge_id" {
    null = false
    type = character_varying(512)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "external_knowledge_bindings_dataset_idx" {
    columns = [column.dataset_id]
  }
  index "external_knowledge_bindings_external_knowledge_api_idx" {
    columns = [column.external_knowledge_api_id]
  }
  index "external_knowledge_bindings_external_knowledge_idx" {
    columns = [column.external_knowledge_id]
  }
  index "external_knowledge_bindings_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "human_input_form_deliveries" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "form_id" {
    null = false
    type = uuid
  }
  column "delivery_method_type" {
    null = false
    type = character_varying(20)
  }
  column "delivery_config_id" {
    null = true
    type = uuid
  }
  column "channel_payload" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "human_input_form_deliveries_form_id_idx" {
    columns = [column.form_id]
  }
}
table "human_input_form_recipients" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "form_id" {
    null = false
    type = uuid
  }
  column "delivery_id" {
    null = false
    type = uuid
  }
  column "recipient_type" {
    null = false
    type = character_varying(20)
  }
  column "recipient_payload" {
    null = false
    type = text
  }
  column "access_token" {
    null = false
    type = character_varying(32)
  }
  primary_key {
    columns = [column.id]
  }
  index "human_input_form_recipients_delivery_id_idx" {
    columns = [column.delivery_id]
  }
  index "human_input_form_recipients_form_id_idx" {
    columns = [column.form_id]
  }
  unique "human_input_form_recipients_access_token_key" {
    columns = [column.access_token]
  }
}
table "human_input_forms" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_run_id" {
    null = true
    type = uuid
  }
  column "form_kind" {
    null = false
    type = character_varying(20)
  }
  column "node_id" {
    null = false
    type = character_varying(60)
  }
  column "form_definition" {
    null = false
    type = text
  }
  column "rendered_content" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = character_varying(20)
  }
  column "expiration_time" {
    null = false
    type = timestamp
  }
  column "selected_action_id" {
    null = true
    type = character_varying(200)
  }
  column "submitted_data" {
    null = true
    type = text
  }
  column "submitted_at" {
    null = true
    type = timestamp
  }
  column "submission_user_id" {
    null = true
    type = uuid
  }
  column "submission_end_user_id" {
    null = true
    type = uuid
  }
  column "completed_by_recipient_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "human_input_forms_status_created_at_idx" {
    columns = [column.status, column.created_at]
  }
  index "human_input_forms_status_expiration_time_idx" {
    columns = [column.status, column.expiration_time]
  }
  index "human_input_forms_workflow_run_id_node_id_idx" {
    columns = [column.workflow_run_id, column.node_id]
  }
}
table "install_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "status" {
    null = false
    type = text
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "total_plugins" {
    null = false
    type = bigint
  }
  column "completed_plugins" {
    null = false
    type = bigint
  }
  column "plugins" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "installed_apps" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "app_owner_tenant_id" {
    null = false
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "is_pinned" {
    null    = false
    type    = boolean
    default = false
  }
  column "last_used_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "installed_app_app_id_idx" {
    columns = [column.app_id]
  }
  index "installed_app_tenant_id_idx" {
    columns = [column.tenant_id]
  }
  unique "unique_tenant_app" {
    columns = [column.tenant_id, column.app_id]
  }
}
table "invitation_codes" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "batch" {
    null = false
    type = character_varying(255)
  }
  column "code" {
    null = false
    type = character_varying(32)
  }
  column "status" {
    null    = false
    type    = character_varying(16)
    default = "unused"
  }
  column "used_at" {
    null = true
    type = timestamp
  }
  column "used_by_tenant_id" {
    null = true
    type = uuid
  }
  column "used_by_account_id" {
    null = true
    type = uuid
  }
  column "deprecated_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "invitation_codes_batch_idx" {
    columns = [column.batch]
  }
  index "invitation_codes_code_idx" {
    columns = [column.code, column.status]
  }
}
table "load_balancing_model_configs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "model_type" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_config" {
    null = true
    type = text
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "credential_id" {
    null = true
    type = uuid
  }
  column "credential_source_type" {
    null = true
    type = character_varying(40)
  }
  primary_key {
    columns = [column.id]
  }
  index "load_balancing_model_config_tenant_provider_model_idx" {
    columns = [column.tenant_id, column.provider_name, column.model_type]
  }
}
table "message_agent_thoughts" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "message_chain_id" {
    null = true
    type = uuid
  }
  column "position" {
    null = false
    type = integer
  }
  column "thought" {
    null = true
    type = text
  }
  column "tool" {
    null = true
    type = text
  }
  column "tool_input" {
    null = true
    type = text
  }
  column "observation" {
    null = true
    type = text
  }
  column "tool_process_data" {
    null = true
    type = text
  }
  column "message" {
    null = true
    type = text
  }
  column "message_token" {
    null = true
    type = integer
  }
  column "message_unit_price" {
    null = true
    type = numeric
  }
  column "answer" {
    null = true
    type = text
  }
  column "answer_token" {
    null = true
    type = integer
  }
  column "answer_unit_price" {
    null = true
    type = numeric
  }
  column "tokens" {
    null = true
    type = integer
  }
  column "total_price" {
    null = true
    type = numeric
  }
  column "currency" {
    null = true
    type = character_varying
  }
  column "latency" {
    null = true
    type = double_precision
  }
  column "created_by_role" {
    null = false
    type = character_varying
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "message_price_unit" {
    null    = false
    type    = numeric(10,7)
    default = 0.001
  }
  column "answer_price_unit" {
    null    = false
    type    = numeric(10,7)
    default = 0.001
  }
  column "message_files" {
    null = true
    type = text
  }
  column "tool_labels_str" {
    null    = false
    type    = text
    default = "{}"
  }
  column "tool_meta_str" {
    null    = false
    type    = text
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  index "message_agent_thought_message_chain_id_idx" {
    columns = [column.message_chain_id]
  }
  index "message_agent_thought_message_id_idx" {
    columns = [column.message_id]
  }
}
table "message_annotations" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = true
    type = uuid
  }
  column "message_id" {
    null = true
    type = uuid
  }
  column "content" {
    null = false
    type = text
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "question" {
    null = false
    type = text
  }
  column "hit_count" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "message_annotation_app_idx" {
    columns = [column.app_id]
  }
  index "message_annotation_conversation_idx" {
    columns = [column.conversation_id]
  }
  index "message_annotation_message_idx" {
    columns = [column.message_id]
  }
}
table "message_chains" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "input" {
    null = true
    type = text
  }
  column "output" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "message_chain_message_id_idx" {
    columns = [column.message_id]
  }
}
table "message_feedbacks" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "rating" {
    null = false
    type = character_varying(255)
  }
  column "content" {
    null = true
    type = text
  }
  column "from_source" {
    null = false
    type = character_varying(255)
  }
  column "from_end_user_id" {
    null = true
    type = uuid
  }
  column "from_account_id" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "message_feedback_app_idx" {
    columns = [column.app_id]
  }
  index "message_feedback_conversation_idx" {
    columns = [column.conversation_id, column.from_source, column.rating]
  }
  index "message_feedback_message_idx" {
    columns = [column.message_id, column.from_source]
  }
}
table "message_files" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "transfer_method" {
    null = false
    type = character_varying(255)
  }
  column "url" {
    null = true
    type = text
  }
  column "upload_file_id" {
    null = true
    type = uuid
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "belongs_to" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "message_file_created_by_idx" {
    columns = [column.created_by]
  }
  index "message_file_message_idx" {
    columns = [column.message_id]
  }
}
table "messages" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "model_provider" {
    null = true
    type = character_varying(255)
  }
  column "model_id" {
    null = true
    type = character_varying(255)
  }
  column "override_model_configs" {
    null = true
    type = text
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "inputs" {
    null = false
    type = json
  }
  column "query" {
    null = false
    type = text
  }
  column "message" {
    null = false
    type = json
  }
  column "message_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "message_unit_price" {
    null = false
    type = numeric(10,4)
  }
  column "answer" {
    null = false
    type = text
  }
  column "answer_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "answer_unit_price" {
    null = false
    type = numeric(10,4)
  }
  column "provider_response_latency" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "total_price" {
    null = true
    type = numeric(10,7)
  }
  column "currency" {
    null = false
    type = character_varying(255)
  }
  column "from_source" {
    null = false
    type = character_varying(255)
  }
  column "from_end_user_id" {
    null = true
    type = uuid
  }
  column "from_account_id" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "agent_based" {
    null    = false
    type    = boolean
    default = false
  }
  column "message_price_unit" {
    null    = false
    type    = numeric(10,7)
    default = 0.001
  }
  column "answer_price_unit" {
    null    = false
    type    = numeric(10,7)
    default = 0.001
  }
  column "workflow_run_id" {
    null = true
    type = uuid
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "normal"
  }
  column "error" {
    null = true
    type = text
  }
  column "message_metadata" {
    null = true
    type = text
  }
  column "invoke_from" {
    null = true
    type = character_varying(255)
  }
  column "parent_message_id" {
    null = true
    type = uuid
  }
  column "app_mode" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "message_account_idx" {
    columns = [column.app_id, column.from_source, column.from_account_id]
  }
  index "message_app_id_idx" {
    columns = [column.app_id, column.created_at]
  }
  index "message_app_mode_idx" {
    columns = [column.app_mode]
  }
  index "message_conversation_id_idx" {
    columns = [column.conversation_id]
  }
  index "message_created_at_id_idx" {
    columns = [column.created_at, column.id]
  }
  index "message_end_user_idx" {
    columns = [column.app_id, column.from_source, column.from_end_user_id]
  }
  index "message_workflow_run_id_idx" {
    columns = [column.conversation_id, column.workflow_run_id]
  }
}
table "oauth_provider_apps" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "app_icon" {
    null = false
    type = character_varying(255)
  }
  column "app_label" {
    null    = false
    type    = json
    default = "{}"
  }
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "client_secret" {
    null = false
    type = character_varying(255)
  }
  column "redirect_uris" {
    null    = false
    type    = json
    default = "[]"
  }
  column "scope" {
    null    = false
    type    = character_varying(255)
    default = "read:name read:email read:avatar read:interface_language read:timezone"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "oauth_provider_app_client_id_idx" {
    columns = [column.client_id]
  }
}
table "operation_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "action" {
    null = false
    type = character_varying(255)
  }
  column "content" {
    null = true
    type = json
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "created_ip" {
    null = false
    type = character_varying(255)
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "operation_log_account_action_idx" {
    columns = [column.tenant_id, column.account_id, column.action]
  }
}
table "pinned_conversations" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "created_by_role" {
    null    = false
    type    = character_varying(255)
    default = "end_user"
  }
  primary_key {
    columns = [column.id]
  }
  index "pinned_conversation_conversation_idx" {
    columns = [column.app_id, column.conversation_id, column.created_by_role, column.created_by]
  }
}
table "pipeline_built_in_templates" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "chunk_structure" {
    null = false
    type = character_varying(255)
  }
  column "icon" {
    null = false
    type = json
  }
  column "yaml_content" {
    null = false
    type = text
  }
  column "copyright" {
    null = false
    type = character_varying(255)
  }
  column "privacy_policy" {
    null = false
    type = character_varying(255)
  }
  column "position" {
    null = false
    type = integer
  }
  column "install_count" {
    null = false
    type = integer
  }
  column "language" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
}
table "pipeline_customized_templates" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "chunk_structure" {
    null = false
    type = character_varying(255)
  }
  column "icon" {
    null = false
    type = json
  }
  column "position" {
    null = false
    type = integer
  }
  column "yaml_content" {
    null = false
    type = text
  }
  column "install_count" {
    null = false
    type = integer
  }
  column "language" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "pipeline_customized_template_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "pipeline_recommended_plugins" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "plugin_id" {
    null = false
    type = text
  }
  column "provider_name" {
    null = false
    type = text
  }
  column "position" {
    null = false
    type = integer
  }
  column "active" {
    null = false
    type = boolean
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "type" {
    null    = false
    type    = character_varying(50)
    default = "tool"
  }
  primary_key {
    columns = [column.id]
  }
}
table "pipelines" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null    = false
    type    = text
    default = ""
  }
  column "workflow_id" {
    null = true
    type = uuid
  }
  column "is_public" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_published" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_by" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
}
table "plugin_declarations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  column "declaration" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_plugin_declarations_plugin_id" {
    columns = [column.plugin_id]
  }
  unique "uni_plugin_declarations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
}
table "plugin_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "runtime_type" {
    null = true
    type = character_varying(127)
  }
  column "endpoints_setups" {
    null = true
    type = bigint
  }
  column "endpoints_active" {
    null = true
    type = bigint
  }
  column "source" {
    null = true
    type = character_varying(63)
  }
  column "meta" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_plugin_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_plugin_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_plugin_installations_tenant_id" {
    columns = [column.tenant_id]
  }
  index "idx_tenant_plugin" {
    unique  = true
    columns = [column.tenant_id, column.plugin_id]
  }
}
table "plugin_readme_records" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "plugin_unique_identifier" {
    null = false
    type = character_varying(255)
  }
  column "language" {
    null = false
    type = character_varying(10)
  }
  column "content" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_plugin_readme_records_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
}
table "plugins" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  column "refers" {
    null    = true
    type    = bigint
    default = 0
  }
  column "install_type" {
    null = true
    type = character_varying(127)
  }
  column "manifest_type" {
    null = true
    type = character_varying(127)
  }
  column "remote_declaration" {
    null = true
    type = text
  }
  column "source" {
    null    = true
    type    = character_varying(63)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_plugins_install_type" {
    columns = [column.install_type]
  }
  index "idx_plugins_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_plugins_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
}
table "provider_credentials" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "credential_name" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_config" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_credential_tenant_provider_idx" {
    columns = [column.tenant_id, column.provider_name]
  }
}
table "provider_model_credentials" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "model_type" {
    null = false
    type = character_varying(40)
  }
  column "credential_name" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_config" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_model_credential_tenant_provider_model_idx" {
    columns = [column.tenant_id, column.provider_name, column.model_name, column.model_type]
  }
}
table "provider_model_settings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "model_type" {
    null = false
    type = character_varying(40)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "load_balancing_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_model_setting_tenant_provider_model_idx" {
    columns = [column.tenant_id, column.provider_name, column.model_type]
  }
}
table "provider_models" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "model_type" {
    null = false
    type = character_varying(40)
  }
  column "is_valid" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "credential_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_model_tenant_id_provider_idx" {
    columns = [column.tenant_id, column.provider_name]
  }
  unique "unique_provider_model_name" {
    columns = [column.tenant_id, column.provider_name, column.model_name, column.model_type]
  }
}
table "provider_orders" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "payment_product_id" {
    null = false
    type = character_varying(191)
  }
  column "payment_id" {
    null = true
    type = character_varying(191)
  }
  column "transaction_id" {
    null = true
    type = character_varying(191)
  }
  column "quantity" {
    null    = false
    type    = integer
    default = 1
  }
  column "currency" {
    null = true
    type = character_varying(40)
  }
  column "total_amount" {
    null = true
    type = integer
  }
  column "payment_status" {
    null    = false
    type    = character_varying(40)
    default = "wait_pay"
  }
  column "paid_at" {
    null = true
    type = timestamp
  }
  column "pay_failed_at" {
    null = true
    type = timestamp
  }
  column "refunded_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_order_tenant_provider_idx" {
    columns = [column.tenant_id, column.provider_name]
  }
}
table "providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "provider_type" {
    null    = false
    type    = character_varying(40)
    default = "custom"
  }
  column "is_valid" {
    null    = false
    type    = boolean
    default = false
  }
  column "last_used" {
    null = true
    type = timestamp
  }
  column "quota_type" {
    null    = true
    type    = character_varying(40)
    default = ""
  }
  column "quota_limit" {
    null = true
    type = bigint
  }
  column "quota_used" {
    null = true
    type = bigint
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "credential_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "provider_tenant_id_provider_idx" {
    columns = [column.tenant_id, column.provider_name]
  }
  unique "unique_provider_name_type_quota" {
    columns = [column.tenant_id, column.provider_name, column.provider_type, column.quota_type]
  }
}
table "rate_limit_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "subscription_plan" {
    null = false
    type = character_varying(255)
  }
  column "operation" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "rate_limit_log_operation_idx" {
    columns = [column.operation]
  }
  index "rate_limit_log_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "recommended_apps" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "description" {
    null = false
    type = json
  }
  column "copyright" {
    null = false
    type = character_varying(255)
  }
  column "privacy_policy" {
    null = false
    type = character_varying(255)
  }
  column "category" {
    null = false
    type = character_varying(255)
  }
  column "position" {
    null = false
    type = integer
  }
  column "is_listed" {
    null = false
    type = boolean
  }
  column "install_count" {
    null = false
    type = integer
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "language" {
    null    = false
    type    = character_varying(255)
    default = "en-US"
  }
  column "custom_disclaimer" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "recommended_app_app_id_idx" {
    columns = [column.app_id]
  }
  index "recommended_app_is_listed_idx" {
    columns = [column.is_listed, column.language]
  }
}
table "saved_messages" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "message_id" {
    null = false
    type = uuid
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "created_by_role" {
    null    = false
    type    = character_varying(255)
    default = "end_user"
  }
  primary_key {
    columns = [column.id]
  }
  index "saved_message_message_id_idx" {
    columns = [column.message_id]
  }
  index "saved_message_message_idx" {
    columns = [column.app_id, column.message_id, column.created_by_role, column.created_by]
  }
}
table "segment_attachment_bindings" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "dataset_id" {
    null = false
    type = uuid
  }
  column "document_id" {
    null = false
    type = uuid
  }
  column "segment_id" {
    null = false
    type = uuid
  }
  column "attachment_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "segment_attachment_binding_attachment_idx" {
    columns = [column.attachment_id]
  }
  index "segment_attachment_binding_tenant_dataset_document_segment_idx" {
    columns = [column.tenant_id, column.dataset_id, column.document_id, column.segment_id]
  }
}
table "serverless_runtimes" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "function_url" {
    null = true
    type = character_varying(255)
  }
  column "function_name" {
    null = true
    type = character_varying(127)
  }
  column "type" {
    null = true
    type = character_varying(127)
  }
  column "checksum" {
    null = true
    type = character_varying(127)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_serverless_runtimes_checksum" {
    columns = [column.checksum]
  }
  unique "uni_serverless_runtimes_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
}
table "sites" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "icon" {
    null = true
    type = character_varying(255)
  }
  column "icon_background" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = text
  }
  column "default_language" {
    null = false
    type = character_varying(255)
  }
  column "copyright" {
    null = true
    type = character_varying(255)
  }
  column "privacy_policy" {
    null = true
    type = character_varying(255)
  }
  column "customize_domain" {
    null = true
    type = character_varying(255)
  }
  column "customize_token_strategy" {
    null = false
    type = character_varying(255)
  }
  column "prompt_public" {
    null    = false
    type    = boolean
    default = false
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "normal"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "code" {
    null = true
    type = character_varying(255)
  }
  column "custom_disclaimer" {
    null = false
    type = text
  }
  column "show_workflow_steps" {
    null    = false
    type    = boolean
    default = true
  }
  column "chat_color_theme" {
    null = true
    type = character_varying(255)
  }
  column "chat_color_theme_inverted" {
    null    = false
    type    = boolean
    default = false
  }
  column "icon_type" {
    null = true
    type = character_varying(255)
  }
  column "created_by" {
    null = true
    type = uuid
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "use_icon_as_answer_icon" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "site_app_id_idx" {
    columns = [column.app_id]
  }
  index "site_code_idx" {
    columns = [column.code, column.status]
  }
}
table "tag_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "tag_id" {
    null = true
    type = uuid
  }
  column "target_id" {
    null = true
    type = uuid
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "tag_bind_tag_id_idx" {
    columns = [column.tag_id]
  }
  index "tag_bind_target_id_idx" {
    columns = [column.target_id]
  }
}
table "tags" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "tag_name_idx" {
    columns = [column.name]
  }
  index "tag_type_idx" {
    columns = [column.type]
  }
}
table "tenant_account_joins" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "account_id" {
    null = false
    type = uuid
  }
  column "role" {
    null    = false
    type    = character_varying(16)
    default = "normal"
  }
  column "invited_by" {
    null = true
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "current" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "tenant_account_join_account_id_idx" {
    columns = [column.account_id]
  }
  index "tenant_account_join_tenant_id_idx" {
    columns = [column.tenant_id]
  }
  unique "unique_tenant_account_join" {
    columns = [column.tenant_id, column.account_id]
  }
}
table "tenant_credit_pools" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "pool_type" {
    null    = false
    type    = character_varying(40)
    default = "trial"
  }
  column "quota_limit" {
    null = false
    type = bigint
  }
  column "quota_used" {
    null = false
    type = bigint
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "tenant_credit_pool_pool_type_idx" {
    columns = [column.pool_type]
  }
  index "tenant_credit_pool_tenant_id_idx" {
    columns = [column.tenant_id]
  }
}
table "tenant_default_models" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "model_name" {
    null = false
    type = character_varying(255)
  }
  column "model_type" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "tenant_default_model_tenant_id_provider_type_idx" {
    columns = [column.tenant_id, column.provider_name, column.model_type]
  }
  unique "unique_tenant_default_model_type" {
    columns = [column.tenant_id, column.model_type]
  }
}
table "tenant_plugin_auto_upgrade_strategies" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "strategy_setting" {
    null    = false
    type    = character_varying(16)
    default = "fix_only"
  }
  column "upgrade_time_of_day" {
    null = false
    type = integer
  }
  column "upgrade_mode" {
    null    = false
    type    = character_varying(16)
    default = "exclude"
  }
  column "exclude_plugins" {
    null = false
    type = json
  }
  column "include_plugins" {
    null = false
    type = json
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_tenant_plugin_auto_upgrade_strategy" {
    columns = [column.tenant_id]
  }
}
table "tenant_preferred_model_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_name" {
    null = false
    type = character_varying(255)
  }
  column "preferred_provider_type" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "tenant_preferred_model_provider_tenant_provider_idx" {
    columns = [column.tenant_id, column.provider_name]
  }
}
table "tenant_storages" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = false
    type = character_varying(255)
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "size" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_tenant_storages_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_tenant_storages_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "tenants" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "encrypt_public_key" {
    null = true
    type = text
  }
  column "plan" {
    null    = false
    type    = character_varying(255)
    default = "basic"
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "normal"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "custom_config" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "tidb_auth_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "cluster_id" {
    null = false
    type = character_varying(255)
  }
  column "cluster_name" {
    null = false
    type = character_varying(255)
  }
  column "active" {
    null    = false
    type    = boolean
    default = false
  }
  column "status" {
    null    = false
    type    = character_varying(255)
    default = "CREATING"
  }
  column "account" {
    null = false
    type = character_varying(255)
  }
  column "password" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "tidb_auth_bindings_active_idx" {
    columns = [column.active]
  }
  index "tidb_auth_bindings_created_at_idx" {
    columns = [column.created_at]
  }
  index "tidb_auth_bindings_status_idx" {
    columns = [column.status]
  }
  index "tidb_auth_bindings_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "tool_api_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "schema" {
    null = false
    type = text
  }
  column "schema_type_str" {
    null = false
    type = character_varying(40)
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "tools_str" {
    null = false
    type = text
  }
  column "icon" {
    null = false
    type = character_varying(255)
  }
  column "credentials_str" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "privacy_policy" {
    null = true
    type = character_varying(255)
  }
  column "custom_disclaimer" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_api_tool_provider" {
    columns = [column.name, column.tenant_id]
  }
}
table "tool_builtin_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(256)
  }
  column "encrypted_credentials" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "name" {
    null    = false
    type    = character_varying(256)
    default = "API KEY 1"
  }
  column "is_default" {
    null    = false
    type    = boolean
    default = false
  }
  column "credential_type" {
    null    = false
    type    = character_varying(32)
    default = "api-key"
  }
  column "expires_at" {
    null    = false
    type    = bigint
    default = -1
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_builtin_tool_provider" {
    columns = [column.tenant_id, column.provider, column.name]
  }
}
table "tool_conversation_variables" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "variables_str" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "conversation_id_idx" {
    columns = [column.conversation_id]
  }
  index "user_id_idx" {
    columns = [column.user_id]
  }
}
table "tool_files" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = true
    type = uuid
  }
  column "file_key" {
    null = false
    type = character_varying(255)
  }
  column "mimetype" {
    null = false
    type = character_varying(255)
  }
  column "original_url" {
    null = true
    type = character_varying(2048)
  }
  column "name" {
    null = false
    type = character_varying
  }
  column "size" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "tool_file_conversation_id_idx" {
    columns = [column.conversation_id]
  }
}
table "tool_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(127)
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_tool_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_tool_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_tool_installations_provider" {
    columns = [column.provider]
  }
  index "idx_tool_installations_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "tool_label_bindings" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tool_id" {
    null = false
    type = character_varying(64)
  }
  column "tool_type" {
    null = false
    type = character_varying(40)
  }
  column "label_name" {
    null = false
    type = character_varying(40)
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_tool_label_bind" {
    columns = [column.tool_id, column.label_name]
  }
}
table "tool_mcp_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(40)
  }
  column "server_identifier" {
    null = false
    type = character_varying(64)
  }
  column "server_url" {
    null = false
    type = text
  }
  column "server_url_hash" {
    null = false
    type = character_varying(64)
  }
  column "icon" {
    null = true
    type = character_varying(255)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "encrypted_credentials" {
    null = true
    type = text
  }
  column "authed" {
    null = false
    type = boolean
  }
  column "tools" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "timeout" {
    null    = false
    type    = double_precision
    default = 30
  }
  column "sse_read_timeout" {
    null    = false
    type    = double_precision
    default = 300
  }
  column "encrypted_headers" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_mcp_provider_name" {
    columns = [column.tenant_id, column.name]
  }
  unique "unique_mcp_provider_server_identifier" {
    columns = [column.tenant_id, column.server_identifier]
  }
  unique "unique_mcp_provider_server_url" {
    columns = [column.tenant_id, column.server_url_hash]
  }
}
table "tool_model_invokes" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "tool_type" {
    null = false
    type = character_varying(40)
  }
  column "tool_name" {
    null = false
    type = character_varying(128)
  }
  column "model_parameters" {
    null = false
    type = text
  }
  column "prompt_messages" {
    null = false
    type = text
  }
  column "model_response" {
    null = false
    type = text
  }
  column "prompt_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "answer_tokens" {
    null    = false
    type    = integer
    default = 0
  }
  column "answer_unit_price" {
    null = false
    type = numeric(10,4)
  }
  column "answer_price_unit" {
    null    = false
    type    = numeric(10,7)
    default = 0.001
  }
  column "provider_response_latency" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "total_price" {
    null = true
    type = numeric(10,7)
  }
  column "currency" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
}
table "tool_oauth_system_clients" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "plugin_id" {
    null = false
    type = character_varying(512)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_oauth_params" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  unique "tool_oauth_system_client_plugin_id_provider_idx" {
    columns = [column.plugin_id, column.provider]
  }
}
table "tool_oauth_tenant_clients" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "encrypted_oauth_params" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_tool_oauth_tenant_client" {
    columns = [column.tenant_id, column.plugin_id, column.provider]
  }
}
table "tool_published_apps" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "description" {
    null = false
    type = text
  }
  column "llm_description" {
    null = false
    type = text
  }
  column "query_description" {
    null = false
    type = text
  }
  column "query_name" {
    null = false
    type = character_varying(40)
  }
  column "tool_name" {
    null = false
    type = character_varying(40)
  }
  column "author" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tool_published_apps_app_id_fkey" {
    columns     = [column.app_id]
    ref_columns = [table.apps.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "unique_published_app_tool" {
    columns = [column.app_id, column.user_id]
  }
}
table "tool_workflow_providers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "icon" {
    null = false
    type = character_varying(255)
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "description" {
    null = false
    type = text
  }
  column "parameter_configuration" {
    null    = false
    type    = text
    default = "[]"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "privacy_policy" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "version" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "label" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_workflow_tool_provider" {
    columns = [column.name, column.tenant_id]
  }
  unique "unique_workflow_tool_provider_app_id" {
    columns = [column.tenant_id, column.app_id]
  }
}
table "trace_app_config" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "tracing_provider" {
    null = true
    type = character_varying(255)
  }
  column "tracing_config" {
    null = true
    type = json
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  column "is_active" {
    null    = false
    type    = boolean
    default = true
  }
  primary_key {
    columns = [column.id]
  }
  index "trace_app_config_app_id_idx" {
    columns = [column.app_id]
  }
}
table "trial_apps" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "trial_limit" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "trial_app_app_id_idx" {
    columns = [column.app_id]
  }
  index "trial_app_tenant_id_idx" {
    columns = [column.tenant_id]
  }
  unique "unique_trail_app_id" {
    columns = [column.app_id]
  }
}
table "trigger_installations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null = true
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider" {
    null = false
    type = character_varying(127)
  }
  column "plugin_unique_identifier" {
    null = true
    type = character_varying(255)
  }
  column "plugin_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_trigger_installations_plugin_id" {
    columns = [column.plugin_id]
  }
  index "idx_trigger_installations_plugin_unique_identifier" {
    columns = [column.plugin_unique_identifier]
  }
  index "idx_trigger_installations_provider" {
    columns = [column.provider]
  }
  index "idx_trigger_installations_tenant_id" {
    columns = [column.tenant_id]
  }
}
table "trigger_oauth_system_clients" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "encrypted_oauth_params" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "trigger_oauth_system_client_plugin_id_provider_idx" {
    columns = [column.plugin_id, column.provider]
  }
}
table "trigger_oauth_tenant_clients" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "plugin_id" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "encrypted_oauth_params" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "unique_trigger_oauth_tenant_client" {
    columns = [column.tenant_id, column.plugin_id, column.provider]
  }
}
table "trigger_subscriptions" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "name" {
    null    = false
    type    = character_varying(255)
    comment = "Subscription instance name"
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "provider_id" {
    null    = false
    type    = character_varying(255)
    comment = "Provider identifier (e.g., plugin_id/provider_name)"
  }
  column "endpoint_id" {
    null    = false
    type    = character_varying(255)
    comment = "Subscription endpoint"
  }
  column "parameters" {
    null    = false
    type    = json
    comment = "Subscription parameters JSON"
  }
  column "properties" {
    null    = false
    type    = json
    comment = "Subscription properties JSON"
  }
  column "credentials" {
    null    = false
    type    = json
    comment = "Subscription credentials JSON"
  }
  column "credential_type" {
    null    = false
    type    = character_varying(50)
    comment = "oauth or api_key"
  }
  column "credential_expires_at" {
    null    = false
    type    = integer
    comment = "OAuth token expiration timestamp, -1 for never"
  }
  column "expires_at" {
    null    = false
    type    = integer
    comment = "Subscription instance expiration timestamp, -1 for never"
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_trigger_providers_endpoint" {
    unique  = true
    columns = [column.endpoint_id]
  }
  index "idx_trigger_providers_tenant_endpoint" {
    columns = [column.tenant_id, column.endpoint_id]
  }
  index "idx_trigger_providers_tenant_provider" {
    columns = [column.tenant_id, column.provider_id]
  }
  unique "unique_trigger_provider" {
    columns = [column.tenant_id, column.provider_id, column.name]
  }
}
table "upload_files" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "storage_type" {
    null = false
    type = character_varying(255)
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "size" {
    null = false
    type = integer
  }
  column "extension" {
    null = false
    type = character_varying(255)
  }
  column "mime_type" {
    null = true
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "used" {
    null    = false
    type    = boolean
    default = false
  }
  column "used_by" {
    null = true
    type = uuid
  }
  column "used_at" {
    null = true
    type = timestamp
  }
  column "hash" {
    null = true
    type = character_varying(255)
  }
  column "created_by_role" {
    null    = false
    type    = character_varying(255)
    default = "account"
  }
  column "source_url" {
    null    = false
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "upload_file_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "whitelists" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = true
    type = uuid
  }
  column "category" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "whitelists_tenant_idx" {
    columns = [column.tenant_id]
  }
}
table "workflow_app_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "workflow_run_id" {
    null = false
    type = uuid
  }
  column "created_from" {
    null = false
    type = character_varying(255)
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_app_log_app_idx" {
    columns = [column.tenant_id, column.app_id]
  }
  index "workflow_app_log_workflow_run_id_idx" {
    columns = [column.workflow_run_id]
  }
}
table "workflow_archive_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "log_id" {
    null = true
    type = uuid
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "workflow_run_id" {
    null = false
    type = uuid
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "log_created_at" {
    null = true
    type = timestamp
  }
  column "log_created_from" {
    null = true
    type = character_varying(255)
  }
  column "run_version" {
    null = false
    type = character_varying(255)
  }
  column "run_status" {
    null = false
    type = character_varying(255)
  }
  column "run_triggered_from" {
    null = false
    type = character_varying(255)
  }
  column "run_error" {
    null = true
    type = text
  }
  column "run_elapsed_time" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "run_total_tokens" {
    null    = false
    type    = bigint
    default = 0
  }
  column "run_total_steps" {
    null    = true
    type    = integer
    default = 0
  }
  column "run_created_at" {
    null = false
    type = timestamp
  }
  column "run_finished_at" {
    null = true
    type = timestamp
  }
  column "run_exceptions_count" {
    null    = true
    type    = integer
    default = 0
  }
  column "trigger_metadata" {
    null = true
    type = text
  }
  column "archived_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_archive_log_app_idx" {
    columns = [column.tenant_id, column.app_id]
  }
  index "workflow_archive_log_run_created_at_idx" {
    columns = [column.run_created_at]
  }
  index "workflow_archive_log_workflow_run_id_idx" {
    columns = [column.workflow_run_id]
  }
}
table "workflow_conversation_variables" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "conversation_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "data" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id, column.conversation_id]
  }
  index "workflow_conversation_variables_app_id_idx" {
    columns = [column.app_id]
  }
  index "workflow_conversation_variables_conversation_id_idx" {
    columns = [column.conversation_id]
  }
  index "workflow_conversation_variables_created_at_idx" {
    columns = [column.created_at]
  }
}
table "workflow_draft_variable_files" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "tenant_id" {
    null    = false
    type    = uuid
    comment = "The tenant to which the WorkflowDraftVariableFile belongs, referencing Tenant.id"
  }
  column "app_id" {
    null    = false
    type    = uuid
    comment = "The application to which the WorkflowDraftVariableFile belongs, referencing App.id"
  }
  column "user_id" {
    null    = false
    type    = uuid
    comment = "The owner to of the WorkflowDraftVariableFile, referencing Account.id"
  }
  column "upload_file_id" {
    null    = false
    type    = uuid
    comment = "Reference to UploadFile containing the large variable data"
  }
  column "size" {
    null    = false
    type    = bigint
    comment = "Size of the original variable content in bytes"
  }
  column "length" {
    null    = true
    type    = integer
    comment = "Length of the original variable content. For array and array-like types, this represents the number of elements. For object types, it indicates the number of keys. For other types, the value is NULL."
  }
  column "value_type" {
    null = false
    type = character_varying(20)
  }
  primary_key {
    columns = [column.id]
  }
}
table "workflow_draft_variables" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "last_edited_at" {
    null = true
    type = timestamp
  }
  column "node_id" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = character_varying(255)
  }
  column "selector" {
    null = false
    type = character_varying(255)
  }
  column "value_type" {
    null = false
    type = character_varying(20)
  }
  column "value" {
    null = false
    type = text
  }
  column "visible" {
    null = false
    type = boolean
  }
  column "editable" {
    null = false
    type = boolean
  }
  column "node_execution_id" {
    null = true
    type = uuid
  }
  column "file_id" {
    null    = true
    type    = uuid
    comment = "Reference to WorkflowDraftVariableFile if variable is offloaded to external storage"
  }
  column "is_default_value" {
    null    = false
    type    = boolean
    default = false
    comment = "Indicates whether the current value is the default for a conversation variable. Always `FALSE` for other types of variables."
  }
  column "user_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_draft_variable_file_id_idx" {
    columns = [column.file_id]
  }
  index "workflow_draft_variables_app_id_user_id_key" {
    unique  = true
    columns = [column.app_id, column.user_id, column.node_id, column.name]
  }
}
table "workflow_node_execution_offload" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "node_execution_id" {
    null = true
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(20)
  }
  column "file_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  unique "workflow_node_execution_offload_node_execution_id_key" {
    columns = [column.node_execution_id, column.type]
  }
}
table "workflow_node_executions" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "triggered_from" {
    null = false
    type = character_varying(255)
  }
  column "workflow_run_id" {
    null = true
    type = uuid
  }
  column "index" {
    null = false
    type = integer
  }
  column "predecessor_node_id" {
    null = true
    type = character_varying(255)
  }
  column "node_id" {
    null = false
    type = character_varying(255)
  }
  column "node_type" {
    null = false
    type = character_varying(255)
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "inputs" {
    null = true
    type = text
  }
  column "process_data" {
    null = true
    type = text
  }
  column "outputs" {
    null = true
    type = text
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "error" {
    null = true
    type = text
  }
  column "elapsed_time" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "execution_metadata" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "finished_at" {
    null = true
    type = timestamp
  }
  column "node_execution_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_node_execution_id_idx" {
    columns = [column.tenant_id, column.app_id, column.workflow_id, column.triggered_from, column.node_execution_id]
  }
  index "workflow_node_execution_node_run_idx" {
    columns = [column.tenant_id, column.app_id, column.workflow_id, column.triggered_from, column.node_id]
  }
  index "workflow_node_execution_workflow_run_id_idx" {
    columns = [column.workflow_run_id]
  }
  index "workflow_node_executions_tenant_id_idx" {
    on {
      column = column.tenant_id
    }
    on {
      column = column.workflow_id
    }
    on {
      column = column.node_id
    }
    on {
      desc   = true
      column = column.created_at
    }
  }
}
table "workflow_pause_reasons" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "pause_id" {
    null = false
    type = uuid
  }
  column "type_" {
    null = false
    type = character_varying(20)
  }
  column "form_id" {
    null = false
    type = character_varying(36)
  }
  column "node_id" {
    null = false
    type = character_varying(255)
  }
  column "message" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_pause_reasons_pause_id_idx" {
    columns = [column.pause_id]
  }
}
table "workflow_pauses" {
  schema = schema.public
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "workflow_run_id" {
    null = false
    type = uuid
  }
  column "resumed_at" {
    null = true
    type = timestamp
  }
  column "state_object_key" {
    null = false
    type = character_varying(255)
  }
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  unique "workflow_pauses_workflow_run_id_key" {
    columns = [column.workflow_run_id]
  }
}
table "workflow_plugin_triggers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "node_id" {
    null = false
    type = character_varying(64)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "provider_id" {
    null = false
    type = character_varying(512)
  }
  column "event_name" {
    null = false
    type = character_varying(255)
  }
  column "subscription_id" {
    null = false
    type = character_varying(255)
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_plugin_trigger_tenant_subscription_idx" {
    columns = [column.tenant_id, column.subscription_id, column.event_name]
  }
  unique "uniq_app_node_subscription" {
    columns = [column.app_id, column.node_id]
  }
}
table "workflow_runs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "triggered_from" {
    null = false
    type = character_varying(255)
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "graph" {
    null = true
    type = text
  }
  column "inputs" {
    null = true
    type = text
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "outputs" {
    null = true
    type = text
  }
  column "error" {
    null = true
    type = text
  }
  column "elapsed_time" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "total_tokens" {
    null    = false
    type    = bigint
    default = 0
  }
  column "total_steps" {
    null    = true
    type    = integer
    default = 0
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "finished_at" {
    null = true
    type = timestamp
  }
  column "exceptions_count" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_run_created_at_id_idx" {
    columns = [column.created_at, column.id]
  }
  index "workflow_run_triggerd_from_idx" {
    columns = [column.tenant_id, column.app_id, column.triggered_from]
  }
}
table "workflow_schedule_plans" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "node_id" {
    null = false
    type = character_varying(64)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "cron_expression" {
    null = false
    type = character_varying(255)
  }
  column "timezone" {
    null = false
    type = character_varying(64)
  }
  column "next_run_at" {
    null = true
    type = timestamp
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_schedule_plan_next_idx" {
    columns = [column.next_run_at]
  }
  unique "uniq_app_node" {
    columns = [column.app_id, column.node_id]
  }
}
table "workflow_trigger_logs" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "workflow_id" {
    null = false
    type = uuid
  }
  column "workflow_run_id" {
    null = true
    type = uuid
  }
  column "root_node_id" {
    null = true
    type = character_varying(255)
  }
  column "trigger_metadata" {
    null = false
    type = text
  }
  column "trigger_type" {
    null = false
    type = character_varying(50)
  }
  column "trigger_data" {
    null = false
    type = text
  }
  column "inputs" {
    null = false
    type = text
  }
  column "outputs" {
    null = true
    type = text
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "error" {
    null = true
    type = text
  }
  column "queue_name" {
    null = false
    type = character_varying(100)
  }
  column "celery_task_id" {
    null = true
    type = character_varying(255)
  }
  column "retry_count" {
    null = false
    type = integer
  }
  column "elapsed_time" {
    null = true
    type = double_precision
  }
  column "total_tokens" {
    null = true
    type = integer
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "created_by_role" {
    null = false
    type = character_varying(255)
  }
  column "created_by" {
    null = false
    type = character_varying(255)
  }
  column "triggered_at" {
    null = true
    type = timestamp
  }
  column "finished_at" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_trigger_log_created_at_idx" {
    columns = [column.created_at]
  }
  index "workflow_trigger_log_status_idx" {
    columns = [column.status]
  }
  index "workflow_trigger_log_tenant_app_idx" {
    columns = [column.tenant_id, column.app_id]
  }
  index "workflow_trigger_log_workflow_id_idx" {
    columns = [column.workflow_id]
  }
  index "workflow_trigger_log_workflow_run_idx" {
    columns = [column.workflow_run_id]
  }
}
table "workflow_webhook_triggers" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuidv7()")
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "node_id" {
    null = false
    type = character_varying(64)
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "webhook_id" {
    null = false
    type = character_varying(24)
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_webhook_trigger_tenant_idx" {
    columns = [column.tenant_id]
  }
  unique "uniq_node" {
    columns = [column.app_id, column.node_id]
  }
  unique "uniq_webhook_id" {
    columns = [column.webhook_id]
  }
}
table "workflows" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "tenant_id" {
    null = false
    type = uuid
  }
  column "app_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "graph" {
    null = false
    type = text
  }
  column "features" {
    null = false
    type = text
  }
  column "created_by" {
    null = false
    type = uuid
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP(0)")
  }
  column "updated_by" {
    null = true
    type = uuid
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "environment_variables" {
    null    = false
    type    = text
    default = "{}"
  }
  column "conversation_variables" {
    null    = false
    type    = text
    default = "{}"
  }
  column "marked_name" {
    null    = false
    type    = character_varying
    default = ""
  }
  column "marked_comment" {
    null    = false
    type    = character_varying
    default = ""
  }
  column "rag_pipeline_variables" {
    null    = false
    type    = text
    default = "{}"
  }
  primary_key {
    columns = [column.id]
  }
  index "workflow_version_idx" {
    columns = [column.tenant_id, column.app_id, column.version]
  }
}
schema "public" {
  comment = "standard public schema"
}
