Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "access_key" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "project_id" {
    null = true
    type = integer
  }
  column "secret" {
    null = true
    type = text
  }
  column "environment_id" {
    null = true
    type = integer
  }
  column "user_id" {
    null = true
    type = integer
  }
  column "owner" {
    null    = false
    type    = character_varying(20)
    default = ""
  }
  column "plain" {
    null = true
    type = text
  }
  column "storage_id" {
    null = true
    type = integer
  }
  column "source_storage_id" {
    null = true
    type = integer
  }
  column "source_storage_key" {
    null = true
    type = character_varying(1000)
  }
  column "source_storage_type" {
    null = true
    type = character_varying(10)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "access_key_environment_id_fkey" {
    columns     = [column.environment_id]
    ref_columns = [table.project__environment.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "access_key_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "access_key_source_storage_id_fkey" {
    columns     = [column.source_storage_id]
    ref_columns = [table.project__secret_storage.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "access_key_storage_id_fkey" {
    columns     = [column.storage_id]
    ref_columns = [table.project__secret_storage.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "access_key_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "event" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = true
    type = integer
  }
  column "object_id" {
    null = true
    type = integer
  }
  column "object_type" {
    null    = true
    type    = character_varying(20)
    default = ""
  }
  column "description" {
    null = true
    type = text
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "user_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "event_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "event_user_id_fkey1" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
}
table "event_backup_5784568" {
  schema = schema.public
  column "project_id" {
    null = true
    type = integer
  }
  column "object_id" {
    null = true
    type = integer
  }
  column "object_type" {
    null    = true
    type    = character_varying(20)
    default = ""
  }
  column "description" {
    null = true
    type = text
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "user_id" {
    null = true
    type = integer
  }
  foreign_key "event_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "migrations" {
  schema = schema.public
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "upgraded_date" {
    null = true
    type = timestamp
  }
  column "notes" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.version]
  }
}
table "option" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = character_varying(1000)
  }
  primary_key {
    columns = [column.key]
  }
}
table "project" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "alert" {
    null    = false
    type    = boolean
    default = false
  }
  column "alert_chat" {
    null    = true
    type    = character_varying(30)
    default = ""
  }
  column "max_parallel_tasks" {
    null    = false
    type    = integer
    default = 0
  }
  column "type" {
    null    = true
    type    = character_varying(20)
    default = ""
  }
  column "default_secret_storage_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_default_secret_storage_id_fkey" {
    columns     = [column.default_secret_storage_id]
    ref_columns = [table.project__secret_storage.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "project__environment" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "password" {
    null = true
    type = character_varying(255)
  }
  column "json" {
    null = false
    type = text
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "env" {
    null = true
    type = text
  }
  column "secret_storage_id" {
    null = true
    type = integer
  }
  column "secret_storage_key_prefix" {
    null = true
    type = character_varying(1000)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__environment_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__environment_secret_storage_id_fkey" {
    columns     = [column.secret_storage_id]
    ref_columns = [table.project__secret_storage.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "project__integration" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "template_id" {
    null = false
    type = integer
  }
  column "auth_method" {
    null    = false
    type    = character_varying(15)
    default = "none"
  }
  column "auth_secret_id" {
    null = true
    type = integer
  }
  column "auth_header" {
    null = true
    type = character_varying(255)
  }
  column "searchable" {
    null    = false
    type    = boolean
    default = false
  }
  column "task_params_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__integration_auth_secret_id_fkey" {
    columns     = [column.auth_secret_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "project__integration_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__integration_task_params_id_fkey" {
    columns     = [column.task_params_id]
    ref_columns = [table.project__task_params.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__integration_template_id_fkey" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__integration_alias" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "alias" {
    null = false
    type = character_varying(50)
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "integration_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__integration_alias_integration_id_fkey" {
    columns     = [column.integration_id]
    ref_columns = [table.project__integration.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__integration_alias_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "project__integration_alias_alias_key" {
    columns = [column.alias]
  }
}
table "project__integration_extract_value" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "integration_id" {
    null = false
    type = integer
  }
  column "value_source" {
    null = false
    type = character_varying(255)
  }
  column "body_data_type" {
    null = true
    type = character_varying(255)
  }
  column "key" {
    null = true
    type = character_varying(255)
  }
  column "variable" {
    null = true
    type = character_varying(255)
  }
  column "variable_type" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__integration_extract_value_integration_id_fkey" {
    columns     = [column.integration_id]
    ref_columns = [table.project__integration.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__integration_matcher" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "integration_id" {
    null = false
    type = integer
  }
  column "match_type" {
    null = true
    type = character_varying(255)
  }
  column "method" {
    null = true
    type = character_varying(255)
  }
  column "body_data_type" {
    null = true
    type = character_varying(255)
  }
  column "key" {
    null = true
    type = character_varying(510)
  }
  column "value" {
    null = true
    type = character_varying(510)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__integration_matcher_integration_id_fkey" {
    columns     = [column.integration_id]
    ref_columns = [table.project__integration.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__inventory" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "inventory" {
    null = false
    type = text
  }
  column "ssh_key_id" {
    null = true
    type = integer
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "become_key_id" {
    null = true
    type = integer
  }
  column "template_id" {
    null = true
    type = integer
  }
  column "repository_id" {
    null = true
    type = integer
  }
  column "runner_tag" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__inventory_become_key_id_fkey" {
    columns     = [column.become_key_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__inventory_holder_id_fkey" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "project__inventory_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__inventory_repository_id_fkey" {
    columns     = [column.repository_id]
    ref_columns = [table.project__repository.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "project__inventory_ssh_key_id_fkey" {
    columns     = [column.ssh_key_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "project__invite" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = true
    type = integer
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "role" {
    null = false
    type = character_varying(50)
  }
  column "status" {
    null    = false
    type    = character_varying(50)
    default = "pending"
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "inviter_user_id" {
    null = false
    type = integer
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "expires_at" {
    null = true
    type = timestamp
  }
  column "accepted_at" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__invite_inviter_user_id_fkey" {
    columns     = [column.inviter_user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__invite_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__invite_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "project__invite_project_id_email_key" {
    columns = [column.project_id, column.email]
  }
  unique "project__invite_project_id_user_id_key" {
    columns = [column.project_id, column.user_id]
  }
  unique "project__invite_token_key" {
    columns = [column.token]
  }
}
table "project__repository" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "git_url" {
    null = false
    type = text
  }
  column "ssh_key_id" {
    null = false
    type = integer
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "git_branch" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__repository_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__repository_ssh_key_id_fkey" {
    columns     = [column.ssh_key_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "project__schedule" {
  schema = schema.public
  column "id" {
    null    = false
    type    = integer
    default = sql("nextval('public.project__schedule_id_seq1'::regclass)")
  }
  column "template_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "cron_format" {
    null = false
    type = character_varying(255)
  }
  column "repository_id" {
    null = true
    type = integer
  }
  column "last_commit_hash" {
    null = true
    type = character_varying(64)
  }
  column "name" {
    null    = false
    type    = character_varying(100)
    default = ""
  }
  column "active" {
    null    = false
    type    = boolean
    default = true
  }
  column "task_params_id" {
    null = true
    type = integer
  }
  column "run_at" {
    null = true
    type = timestamp
  }
  column "type" {
    null    = false
    type    = character_varying(20)
    default = ""
  }
  column "delete_after_run" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__schedule_project_id_fkey1" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__schedule_repository_id_fkey1" {
    columns     = [column.repository_id]
    ref_columns = [table.project__repository.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__schedule_task_params_id_fkey" {
    columns     = [column.task_params_id]
    ref_columns = [table.project__task_params.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__schedule_template_id_fkey1" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__secret_storage" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "type" {
    null = false
    type = character_varying(20)
  }
  column "params" {
    null = true
    type = text
  }
  column "readonly" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__secret_storage_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__task_params" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "environment" {
    null = true
    type = text
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "arguments" {
    null = true
    type = text
  }
  column "inventory_id" {
    null = true
    type = integer
  }
  column "git_branch" {
    null = true
    type = character_varying(255)
  }
  column "params" {
    null = true
    type = text
  }
  column "version" {
    null = true
    type = character_varying(20)
  }
  column "message" {
    null = true
    type = character_varying(250)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__task_params_inventory_id_fkey" {
    columns     = [column.inventory_id]
    ref_columns = [table.project__inventory.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__task_params_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__template" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "inventory_id" {
    null = true
    type = integer
  }
  column "repository_id" {
    null = false
    type = integer
  }
  column "environment_id" {
    null = true
    type = integer
  }
  column "playbook" {
    null = false
    type = character_varying(255)
  }
  column "arguments" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = true
    type = text
  }
  column "type" {
    null    = false
    type    = character_varying(10)
    default = ""
  }
  column "start_version" {
    null = true
    type = character_varying(20)
  }
  column "build_template_id" {
    null = true
    type = integer
  }
  column "view_id" {
    null = true
    type = integer
  }
  column "survey_vars" {
    null = true
    type = text
  }
  column "autorun" {
    null    = true
    type    = boolean
    default = false
  }
  column "allow_override_args_in_task" {
    null    = false
    type    = boolean
    default = false
  }
  column "suppress_success_alerts" {
    null    = false
    type    = boolean
    default = false
  }
  column "app" {
    null    = false
    type    = character_varying(50)
    default = ""
  }
  column "tasks" {
    null    = false
    type    = integer
    default = 0
  }
  column "git_branch" {
    null = true
    type = character_varying(255)
  }
  column "task_params" {
    null = true
    type = text
  }
  column "runner_tag" {
    null = true
    type = character_varying(50)
  }
  column "allow_override_branch_in_task" {
    null    = false
    type    = boolean
    default = false
  }
  column "allow_parallel_tasks" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__template_build_template_id_fkey" {
    columns     = [column.build_template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__template_environment_id_fkey" {
    columns     = [column.environment_id]
    ref_columns = [table.project__environment.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__template_inventory_id_fkey" {
    columns     = [column.inventory_id]
    ref_columns = [table.project__inventory.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__template_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__template_repository_id_fkey" {
    columns     = [column.repository_id]
    ref_columns = [table.project__repository.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__template_view_id_fkey" {
    columns     = [column.view_id]
    ref_columns = [table.project__view.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
}
table "project__template_role" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "template_id" {
    null = false
    type = integer
  }
  column "role_slug" {
    null = false
    type = character_varying(100)
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "permissions" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__template_role_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__template_role_role_slug_fkey" {
    columns     = [column.role_slug]
    ref_columns = [table.role.column.slug]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__template_role_template_id_fkey" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "project__template_role_template_id_role_slug_key" {
    columns = [column.template_id, column.role_slug]
  }
}
table "project__template_vault" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "template_id" {
    null = false
    type = integer
  }
  column "vault_key_id" {
    null = true
    type = integer
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null    = false
    type    = character_varying(20)
    default = "password"
  }
  column "script" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__template_vault_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__template_vault_template_id_fkey" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__template_vault_vault_key_id_fkey" {
    columns     = [column.vault_key_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "project__template_vault_template_id_vault_key_id_name_key" {
    columns = [column.template_id, column.vault_key_id, column.name]
  }
}
table "project__terraform_inventory_alias" {
  schema = schema.public
  column "alias" {
    null = false
    type = character_varying(100)
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "inventory_id" {
    null = false
    type = integer
  }
  column "auth_key_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.alias]
  }
  foreign_key "project__terraform_inventory_alias_auth_key_id_fkey" {
    columns     = [column.auth_key_id]
    ref_columns = [table.access_key.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project__terraform_inventory_alias_inventory_id_fkey" {
    columns     = [column.inventory_id]
    ref_columns = [table.project__inventory.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__terraform_inventory_alias_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project__terraform_inventory_state" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "inventory_id" {
    null = false
    type = integer
  }
  column "state" {
    null = false
    type = text
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "task_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__terraform_inventory_state_inventory_id_fkey" {
    columns     = [column.inventory_id]
    ref_columns = [table.project__inventory.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__terraform_inventory_state_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__terraform_inventory_state_task_id_fkey" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
}
table "project__user" {
  schema = schema.public
  column "project_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = false
    type = integer
  }
  column "role" {
    null    = false
    type    = character_varying(50)
    default = "manager"
  }
  foreign_key "project__user_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "project__user_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "project__user_project_id_user_id_key" {
    columns = [column.project_id, column.user_id]
  }
}
table "project__view" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "title" {
    null = false
    type = character_varying(100)
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "position" {
    null = false
    type = integer
  }
  column "hidden" {
    null    = false
    type    = boolean
    default = false
  }
  column "type" {
    null    = false
    type    = character_varying(20)
    default = ""
  }
  column "filter" {
    null = true
    type = character_varying(1000)
  }
  column "sort_column" {
    null = true
    type = character_varying(100)
  }
  column "sort_reverse" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project__view_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "role" {
  schema = schema.public
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "permissions" {
    null    = false
    type    = bigint
    default = 0
  }
  column "project_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.slug]
  }
  foreign_key "role_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "runner" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "project_id" {
    null = true
    type = integer
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "webhook" {
    null    = false
    type    = character_varying(1000)
    default = ""
  }
  column "max_parallel_tasks" {
    null    = false
    type    = integer
    default = 0
  }
  column "name" {
    null    = false
    type    = character_varying(100)
    default = ""
  }
  column "active" {
    null    = false
    type    = boolean
    default = true
  }
  column "public_key" {
    null = true
    type = text
  }
  column "tag" {
    null    = false
    type    = character_varying(200)
    default = ""
  }
  column "touched" {
    null = true
    type = timestamp
  }
  column "cleaning_requested" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "runner_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "session" {
  schema = schema.public
  column "id" {
    null    = false
    type    = integer
    default = sql("nextval('public.session_id_seq1'::regclass)")
  }
  column "user_id" {
    null = false
    type = integer
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "last_active" {
    null = false
    type = timestamp
  }
  column "ip" {
    null    = false
    type    = character_varying(39)
    default = ""
  }
  column "user_agent" {
    null = false
    type = text
  }
  column "expired" {
    null    = false
    type    = boolean
    default = false
  }
  column "verification_method" {
    null    = false
    type    = integer
    default = 0
  }
  column "verified" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "expired" {
    columns = [column.expired]
  }
  index "user_id" {
    columns = [column.user_id]
  }
}
table "task" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "template_id" {
    null = false
    type = integer
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "playbook" {
    null = false
    type = character_varying(255)
  }
  column "environment" {
    null = true
    type = text
  }
  column "created" {
    null = true
    type = timestamp
  }
  column "start" {
    null = true
    type = timestamp
  }
  column "end" {
    null = true
    type = timestamp
  }
  column "user_id" {
    null = true
    type = integer
  }
  column "project_id" {
    null = true
    type = integer
  }
  column "message" {
    null    = false
    type    = character_varying(250)
    default = ""
  }
  column "version" {
    null = true
    type = character_varying(20)
  }
  column "commit_hash" {
    null = true
    type = character_varying(64)
  }
  column "commit_message" {
    null    = false
    type    = character_varying(100)
    default = ""
  }
  column "build_task_id" {
    null = true
    type = integer
  }
  column "arguments" {
    null = true
    type = text
  }
  column "inventory_id" {
    null = true
    type = integer
  }
  column "integration_id" {
    null = true
    type = integer
  }
  column "schedule_id" {
    null = true
    type = integer
  }
  column "git_branch" {
    null = true
    type = character_varying(255)
  }
  column "params" {
    null = true
    type = text
  }
  column "runner_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task_build_task_id_fk_y38rt" {
    columns     = [column.build_task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "task_integration_id_fkey" {
    columns     = [column.integration_id]
    ref_columns = [table.project__integration.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "task_inventory_id_fkey" {
    columns     = [column.inventory_id]
    ref_columns = [table.project__inventory.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "task_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "task_runner_id_fkey" {
    columns     = [column.runner_id]
    ref_columns = [table.runner.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "task_schedule_id_fkey" {
    columns     = [column.schedule_id]
    ref_columns = [table.project__schedule.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "task_template_id_fkey" {
    columns     = [column.template_id]
    ref_columns = [table.project__template.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "task_project_id_idx" {
    columns = [column.project_id]
  }
  index "task_template_id_idx" {
    columns = [column.template_id]
  }
}
table "task__ansible_error" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "task_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "task" {
    null = false
    type = character_varying(250)
  }
  column "error" {
    null = false
    type = character_varying(1000)
  }
  column "host" {
    null = true
    type = character_varying(250)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task__ansible_error_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "task__ansible_error_task_id_fkey" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "task__ansible_host" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "task_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "host" {
    null = false
    type = character_varying(250)
  }
  column "failed" {
    null = false
    type = integer
  }
  column "ignored" {
    null = false
    type = integer
  }
  column "changed" {
    null = false
    type = integer
  }
  column "ok" {
    null = false
    type = integer
  }
  column "rescued" {
    null = false
    type = integer
  }
  column "skipped" {
    null = false
    type = integer
  }
  column "unreachable" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task__ansible_host_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "task__ansible_host_task_id_fkey" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "task__output" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "task_id" {
    null = false
    type = integer
  }
  column "time" {
    null = false
    type = timestamp
  }
  column "output" {
    null = false
    type = text
  }
  column "stage_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task__output_stage_id_fkey" {
    columns     = [column.stage_id]
    ref_columns = [table.task__stage.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "task__output_task_id_fkey1" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "task__output_task_id_idx" {
    columns = [column.task_id]
  }
  index "task__output_time_idx" {
    columns = [column.time]
  }
}
table "task__stage" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "task_id" {
    null = false
    type = integer
  }
  column "start" {
    null = true
    type = timestamp
  }
  column "end" {
    null = true
    type = timestamp
  }
  column "type" {
    null = true
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task__stage_task_id_fkey" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "task__stage_result" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "task_id" {
    null = false
    type = integer
  }
  column "stage_id" {
    null = false
    type = integer
  }
  column "json" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "task__stage_result_stage_id_fkey" {
    columns     = [column.stage_id]
    ref_columns = [table.task__stage.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "task__stage_result_task_id_fkey" {
    columns     = [column.task_id]
    ref_columns = [table.task.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "user" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "username" {
    null = false
    type = character_varying(255)
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
    null = false
    type = character_varying(255)
  }
  column "alert" {
    null    = false
    type    = boolean
    default = false
  }
  column "external" {
    null    = false
    type    = boolean
    default = false
  }
  column "admin" {
    null    = false
    type    = boolean
    default = true
  }
  column "pro" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  unique "user_email_key" {
    columns = [column.email]
  }
  unique "user_username_key" {
    columns = [column.username]
  }
}
table "user__email_otp" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "user_id" {
    null = false
    type = integer
  }
  column "code" {
    null = false
    type = character_varying(250)
  }
  column "created" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user__email_otp_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "user__email_otp_code_key" {
    columns = [column.code]
  }
}
table "user__token" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(44)
  }
  column "created" {
    null = false
    type = timestamp
  }
  column "expired" {
    null    = false
    type    = boolean
    default = false
  }
  column "user_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user__token_user_id_fkey1" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "user__totp" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "user_id" {
    null = false
    type = integer
  }
  column "url" {
    null = false
    type = character_varying(250)
  }
  column "recovery_hash" {
    null = false
    type = character_varying(250)
  }
  column "created" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user__totp_user_id_fkey" {
    columns     = [column.user_id]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "user__totp_user_id_key" {
    columns = [column.user_id]
  }
}
schema "public" {
  comment = "standard public schema"
}
