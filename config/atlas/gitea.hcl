Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "access" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "mode" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_access_s" {
    unique  = true
    columns = [column.user_id, column.repo_id]
  }
}
table "access_token" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "token_hash" {
    null = true
    type = character_varying(255)
  }
  column "token_salt" {
    null = true
    type = character_varying(255)
  }
  column "token_last_eight" {
    null = true
    type = character_varying(255)
  }
  column "scope" {
    null = true
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_access_token_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_access_token_token_last_eight" {
    columns = [column.token_last_eight]
  }
  index "IDX_access_token_uid" {
    columns = [column.uid]
  }
  index "IDX_access_token_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_access_token_token_hash" {
    unique  = true
    columns = [column.token_hash]
  }
}
table "action" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "op_type" {
    null = true
    type = integer
  }
  column "act_user_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "comment_id" {
    null = true
    type = bigint
  }
  column "is_deleted" {
    null    = false
    type    = boolean
    default = false
  }
  column "ref_name" {
    null = true
    type = character_varying(255)
  }
  column "is_private" {
    null    = false
    type    = boolean
    default = false
  }
  column "content" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_au_c_u" {
    columns = [column.act_user_id, column.created_unix, column.user_id]
  }
  index "IDX_action_au_r_c_u_d" {
    columns = [column.act_user_id, column.repo_id, column.created_unix, column.user_id, column.is_deleted]
  }
  index "IDX_action_c_u" {
    columns = [column.user_id, column.is_deleted]
  }
  index "IDX_action_c_u_d" {
    columns = [column.created_unix, column.user_id, column.is_deleted]
  }
  index "IDX_action_comment_id" {
    columns = [column.comment_id]
  }
  index "IDX_action_r_u_d" {
    columns = [column.repo_id, column.user_id, column.is_deleted]
  }
  index "IDX_action_user_id" {
    columns = [column.user_id]
  }
}
table "action_artifact" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "run_id" {
    null = true
    type = bigint
  }
  column "runner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "commit_sha" {
    null = true
    type = character_varying(255)
  }
  column "storage_path" {
    null = true
    type = character_varying(255)
  }
  column "file_size" {
    null = true
    type = bigint
  }
  column "file_compressed_size" {
    null = true
    type = bigint
  }
  column "content_encoding" {
    null = true
    type = character_varying(255)
  }
  column "artifact_path" {
    null = true
    type = character_varying(255)
  }
  column "artifact_name" {
    null = true
    type = character_varying(255)
  }
  column "status" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "expired_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_artifact_artifact_name" {
    columns = [column.artifact_name]
  }
  index "IDX_action_artifact_artifact_path" {
    columns = [column.artifact_path]
  }
  index "IDX_action_artifact_expired_unix" {
    columns = [column.expired_unix]
  }
  index "IDX_action_artifact_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_artifact_run_id" {
    columns = [column.run_id]
  }
  index "IDX_action_artifact_status" {
    columns = [column.status]
  }
  index "IDX_action_artifact_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_action_artifact_runid_name_path" {
    unique  = true
    columns = [column.run_id, column.artifact_path, column.artifact_name]
  }
}
table "action_run" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "workflow_id" {
    null = true
    type = character_varying(255)
  }
  column "index" {
    null = true
    type = bigint
  }
  column "trigger_user_id" {
    null = true
    type = bigint
  }
  column "schedule_id" {
    null = true
    type = bigint
  }
  column "ref" {
    null = true
    type = character_varying(255)
  }
  column "commit_sha" {
    null = true
    type = character_varying(255)
  }
  column "is_fork_pull_request" {
    null = true
    type = boolean
  }
  column "need_approval" {
    null = true
    type = boolean
  }
  column "approved_by" {
    null = true
    type = bigint
  }
  column "event" {
    null = true
    type = character_varying(255)
  }
  column "event_payload" {
    null = true
    type = text
  }
  column "trigger_event" {
    null = true
    type = character_varying(255)
  }
  column "status" {
    null = true
    type = integer
  }
  column "version" {
    null    = true
    type    = integer
    default = 0
  }
  column "started" {
    null = true
    type = bigint
  }
  column "stopped" {
    null = true
    type = bigint
  }
  column "previous_duration" {
    null = true
    type = bigint
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_run_approved_by" {
    columns = [column.approved_by]
  }
  index "IDX_action_run_index" {
    columns = [column.index]
  }
  index "IDX_action_run_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_run_ref" {
    columns = [column.ref]
  }
  index "IDX_action_run_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_run_status" {
    columns = [column.status]
  }
  index "IDX_action_run_trigger_user_id" {
    columns = [column.trigger_user_id]
  }
  index "IDX_action_run_workflow_id" {
    columns = [column.workflow_id]
  }
  index "UQE_action_run_repo_index" {
    unique  = true
    columns = [column.repo_id, column.index]
  }
}
table "action_run_index" {
  schema = schema.public
  column "group_id" {
    null = false
    type = bigint
  }
  column "max_index" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.group_id]
  }
  index "IDX_action_run_index_max_index" {
    columns = [column.max_index]
  }
}
table "action_run_job" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "run_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "commit_sha" {
    null = true
    type = character_varying(255)
  }
  column "is_fork_pull_request" {
    null = true
    type = boolean
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "attempt" {
    null = true
    type = bigint
  }
  column "workflow_payload" {
    null = true
    type = bytea
  }
  column "job_id" {
    null = true
    type = character_varying(255)
  }
  column "needs" {
    null = true
    type = text
  }
  column "runs_on" {
    null = true
    type = text
  }
  column "task_id" {
    null = true
    type = bigint
  }
  column "status" {
    null = true
    type = integer
  }
  column "started" {
    null = true
    type = bigint
  }
  column "stopped" {
    null = true
    type = bigint
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_run_job_commit_sha" {
    columns = [column.commit_sha]
  }
  index "IDX_action_run_job_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_run_job_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_run_job_run_id" {
    columns = [column.run_id]
  }
  index "IDX_action_run_job_status" {
    columns = [column.status]
  }
  index "IDX_action_run_job_updated" {
    columns = [column.updated]
  }
}
table "action_runner" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uuid" {
    null = true
    type = character(36)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "version" {
    null = true
    type = character_varying(64)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "description" {
    null = true
    type = text
  }
  column "base" {
    null = true
    type = integer
  }
  column "repo_range" {
    null = true
    type = character_varying(255)
  }
  column "token_hash" {
    null = true
    type = character_varying(255)
  }
  column "token_salt" {
    null = true
    type = character_varying(255)
  }
  column "last_online" {
    null = true
    type = bigint
  }
  column "last_active" {
    null = true
    type = bigint
  }
  column "agent_labels" {
    null = true
    type = text
  }
  column "ephemeral" {
    null    = false
    type    = boolean
    default = false
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  column "deleted" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_runner_last_active" {
    columns = [column.last_active]
  }
  index "IDX_action_runner_last_online" {
    columns = [column.last_online]
  }
  index "IDX_action_runner_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_runner_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_action_runner_token_hash" {
    unique  = true
    columns = [column.token_hash]
  }
  index "UQE_action_runner_uuid" {
    unique  = true
    columns = [column.uuid]
  }
}
table "action_runner_token" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "token" {
    null = true
    type = character_varying(255)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "is_active" {
    null = true
    type = boolean
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  column "deleted" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_runner_token_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_runner_token_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_action_runner_token_token" {
    unique  = true
    columns = [column.token]
  }
}
table "action_schedule" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "specs" {
    null = true
    type = text
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "workflow_id" {
    null = true
    type = character_varying(255)
  }
  column "trigger_user_id" {
    null = true
    type = bigint
  }
  column "ref" {
    null = true
    type = character_varying(255)
  }
  column "commit_sha" {
    null = true
    type = character_varying(255)
  }
  column "event" {
    null = true
    type = character_varying(255)
  }
  column "event_payload" {
    null = true
    type = text
  }
  column "content" {
    null = true
    type = bytea
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_schedule_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_schedule_repo_id" {
    columns = [column.repo_id]
  }
}
table "action_schedule_spec" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "schedule_id" {
    null = true
    type = bigint
  }
  column "next" {
    null = true
    type = bigint
  }
  column "prev" {
    null = true
    type = bigint
  }
  column "spec" {
    null = true
    type = character_varying(255)
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_schedule_spec_next" {
    columns = [column.next]
  }
  index "IDX_action_schedule_spec_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_schedule_spec_schedule_id" {
    columns = [column.schedule_id]
  }
}
table "action_task" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "job_id" {
    null = true
    type = bigint
  }
  column "attempt" {
    null = true
    type = bigint
  }
  column "runner_id" {
    null = true
    type = bigint
  }
  column "status" {
    null = true
    type = integer
  }
  column "started" {
    null = true
    type = bigint
  }
  column "stopped" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "commit_sha" {
    null = true
    type = character_varying(255)
  }
  column "is_fork_pull_request" {
    null = true
    type = boolean
  }
  column "token_hash" {
    null = true
    type = character_varying(255)
  }
  column "token_salt" {
    null = true
    type = character_varying(255)
  }
  column "token_last_eight" {
    null = true
    type = character_varying(255)
  }
  column "log_filename" {
    null = true
    type = character_varying(255)
  }
  column "log_in_storage" {
    null = true
    type = boolean
  }
  column "log_length" {
    null = true
    type = bigint
  }
  column "log_size" {
    null = true
    type = bigint
  }
  column "log_indexes" {
    null = true
    type = bytea
  }
  column "log_expired" {
    null = true
    type = boolean
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_task_commit_sha" {
    columns = [column.commit_sha]
  }
  index "IDX_action_task_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_action_task_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_task_runner_id" {
    columns = [column.runner_id]
  }
  index "IDX_action_task_started" {
    columns = [column.started]
  }
  index "IDX_action_task_status" {
    columns = [column.status]
  }
  index "IDX_action_task_stopped_log_expired" {
    columns = [column.stopped, column.log_expired]
  }
  index "IDX_action_task_token_last_eight" {
    columns = [column.token_last_eight]
  }
  index "IDX_action_task_updated" {
    columns = [column.updated]
  }
  index "UQE_action_task_token_hash" {
    unique  = true
    columns = [column.token_hash]
  }
}
table "action_task_output" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "task_id" {
    null = true
    type = bigint
  }
  column "output_key" {
    null = true
    type = character_varying(255)
  }
  column "output_value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_task_output_task_id" {
    columns = [column.task_id]
  }
  index "UQE_action_task_output_task_id_output_key" {
    unique  = true
    columns = [column.task_id, column.output_key]
  }
}
table "action_task_step" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "task_id" {
    null = true
    type = bigint
  }
  column "index" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "status" {
    null = true
    type = integer
  }
  column "log_index" {
    null = true
    type = bigint
  }
  column "log_length" {
    null = true
    type = bigint
  }
  column "started" {
    null = true
    type = bigint
  }
  column "stopped" {
    null = true
    type = bigint
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_task_step_index" {
    columns = [column.index]
  }
  index "IDX_action_task_step_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_action_task_step_status" {
    columns = [column.status]
  }
  index "IDX_action_task_step_task_id" {
    columns = [column.task_id]
  }
  index "UQE_action_task_step_task_index" {
    unique  = true
    columns = [column.task_id, column.index]
  }
}
table "action_tasks_version" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "version" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_tasks_version_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_action_tasks_version_owner_repo" {
    unique  = true
    columns = [column.owner_id, column.repo_id]
  }
}
table "action_variable" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "data" {
    null = false
    type = text
  }
  column "description" {
    null = true
    type = text
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_action_variable_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_action_variable_owner_repo_name" {
    unique  = true
    columns = [column.owner_id, column.repo_id, column.name]
  }
}
table "app_state" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(200)
  }
  column "revision" {
    null = true
    type = bigint
  }
  column "content" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "attachment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uuid" {
    null = true
    type = uuid
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "release_id" {
    null = true
    type = bigint
  }
  column "uploader_id" {
    null    = true
    type    = bigint
    default = 0
  }
  column "comment_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "download_count" {
    null    = true
    type    = bigint
    default = 0
  }
  column "size" {
    null    = true
    type    = bigint
    default = 0
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_attachment_comment_id" {
    columns = [column.comment_id]
  }
  index "IDX_attachment_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_attachment_release_id" {
    columns = [column.release_id]
  }
  index "IDX_attachment_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_attachment_uploader_id" {
    columns = [column.uploader_id]
  }
  index "UQE_attachment_uuid" {
    unique  = true
    columns = [column.uuid]
  }
}
table "auth_token" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "token_hash" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "expires_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_auth_token_expires_unix" {
    columns = [column.expires_unix]
  }
  index "IDX_auth_token_user_id" {
    columns = [column.user_id]
  }
}
table "badge" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "slug" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "image_url" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_badge_slug" {
    unique  = true
    columns = [column.slug]
  }
}
table "branch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "commit_id" {
    null = true
    type = character_varying(255)
  }
  column "commit_message" {
    null = true
    type = text
  }
  column "pusher_id" {
    null = true
    type = bigint
  }
  column "is_deleted" {
    null = true
    type = boolean
  }
  column "deleted_by_id" {
    null = true
    type = bigint
  }
  column "deleted_unix" {
    null = true
    type = bigint
  }
  column "commit_time" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_branch_deleted_unix" {
    columns = [column.deleted_unix]
  }
  index "IDX_branch_is_deleted" {
    columns = [column.is_deleted]
  }
  index "UQE_branch_s" {
    unique  = true
    columns = [column.repo_id, column.name]
  }
}
table "collaboration" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "mode" {
    null    = false
    type    = integer
    default = 2
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_collaboration_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_collaboration_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_collaboration_updated_unix" {
    columns = [column.updated_unix]
  }
  index "IDX_collaboration_user_id" {
    columns = [column.user_id]
  }
  index "UQE_collaboration_s" {
    unique  = true
    columns = [column.repo_id, column.user_id]
  }
}
table "comment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = true
    type = integer
  }
  column "poster_id" {
    null = true
    type = bigint
  }
  column "original_author" {
    null = true
    type = character_varying(255)
  }
  column "original_author_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "label_id" {
    null = true
    type = bigint
  }
  column "old_project_id" {
    null = true
    type = bigint
  }
  column "project_id" {
    null = true
    type = bigint
  }
  column "old_milestone_id" {
    null = true
    type = bigint
  }
  column "milestone_id" {
    null = true
    type = bigint
  }
  column "time_id" {
    null = true
    type = bigint
  }
  column "assignee_id" {
    null = true
    type = bigint
  }
  column "removed_assignee" {
    null = true
    type = boolean
  }
  column "assignee_team_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "resolve_doer_id" {
    null = true
    type = bigint
  }
  column "old_title" {
    null = true
    type = character_varying(255)
  }
  column "new_title" {
    null = true
    type = character_varying(255)
  }
  column "old_ref" {
    null = true
    type = character_varying(255)
  }
  column "new_ref" {
    null = true
    type = character_varying(255)
  }
  column "dependent_issue_id" {
    null = true
    type = bigint
  }
  column "commit_id" {
    null = true
    type = bigint
  }
  column "line" {
    null = true
    type = bigint
  }
  column "tree_path" {
    null = true
    type = character_varying(4000)
  }
  column "content" {
    null = true
    type = text
  }
  column "content_version" {
    null    = false
    type    = integer
    default = 0
  }
  column "patch" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "commit_sha" {
    null = true
    type = character_varying(64)
  }
  column "review_id" {
    null = true
    type = bigint
  }
  column "invalidated" {
    null = true
    type = boolean
  }
  column "ref_repo_id" {
    null = true
    type = bigint
  }
  column "ref_issue_id" {
    null = true
    type = bigint
  }
  column "ref_comment_id" {
    null = true
    type = bigint
  }
  column "ref_action" {
    null = true
    type = smallint
  }
  column "ref_is_pull" {
    null = true
    type = boolean
  }
  column "comment_meta_data" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_comment_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_comment_dependent_issue_id" {
    columns = [column.dependent_issue_id]
  }
  index "IDX_comment_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_comment_poster_id" {
    columns = [column.poster_id]
  }
  index "IDX_comment_ref_comment_id" {
    columns = [column.ref_comment_id]
  }
  index "IDX_comment_ref_issue_id" {
    columns = [column.ref_issue_id]
  }
  index "IDX_comment_ref_repo_id" {
    columns = [column.ref_repo_id]
  }
  index "IDX_comment_review_id" {
    columns = [column.review_id]
  }
  index "IDX_comment_type" {
    columns = [column.type]
  }
  index "IDX_comment_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "commit_status" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "index" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "state" {
    null = false
    type = character_varying(7)
  }
  column "sha" {
    null = false
    type = character_varying(64)
  }
  column "target_url" {
    null = true
    type = text
  }
  column "description" {
    null = true
    type = text
  }
  column "context_hash" {
    null = true
    type = character_varying(64)
  }
  column "context" {
    null = true
    type = text
  }
  column "creator_id" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_commit_status_context_hash" {
    columns = [column.context_hash]
  }
  index "IDX_commit_status_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_commit_status_index" {
    columns = [column.index]
  }
  index "IDX_commit_status_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_commit_status_sha" {
    columns = [column.sha]
  }
  index "IDX_commit_status_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_commit_status_repo_sha_index" {
    unique  = true
    columns = [column.index, column.repo_id, column.sha]
  }
}
table "commit_status_index" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "sha" {
    null = true
    type = character_varying(255)
  }
  column "max_index" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_commit_status_index_max_index" {
    columns = [column.max_index]
  }
  index "UQE_commit_status_index_repo_sha" {
    unique  = true
    columns = [column.repo_id, column.sha]
  }
}
table "commit_status_summary" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "sha" {
    null = false
    type = character_varying(64)
  }
  column "state" {
    null = false
    type = character_varying(7)
  }
  column "target_url" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_commit_status_summary_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_commit_status_summary_sha" {
    columns = [column.sha]
  }
  index "UQE_commit_status_summary_repo_id_sha" {
    unique  = true
    columns = [column.repo_id, column.sha]
  }
}
table "dbfs_data" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "revision" {
    null = false
    type = bigint
  }
  column "meta_id" {
    null = false
    type = bigint
  }
  column "blob_offset" {
    null = false
    type = bigint
  }
  column "blob_size" {
    null = false
    type = bigint
  }
  column "blob_data" {
    null = false
    type = bytea
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_dbfs_data_meta_offset" {
    columns = [column.meta_id, column.blob_offset]
  }
}
table "dbfs_meta" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "full_path" {
    null = false
    type = character_varying(500)
  }
  column "block_size" {
    null = false
    type = bigint
  }
  column "file_size" {
    null = false
    type = bigint
  }
  column "create_timestamp" {
    null = false
    type = bigint
  }
  column "modify_timestamp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_dbfs_meta_full_path" {
    unique  = true
    columns = [column.full_path]
  }
}
table "deploy_key" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "key_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "fingerprint" {
    null = true
    type = character_varying(255)
  }
  column "mode" {
    null    = false
    type    = integer
    default = 1
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_deploy_key_key_id" {
    columns = [column.key_id]
  }
  index "IDX_deploy_key_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_deploy_key_s" {
    unique  = true
    columns = [column.key_id, column.repo_id]
  }
}
table "email_address" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = false
    type = bigint
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "lower_email" {
    null = false
    type = character_varying(255)
  }
  column "is_activated" {
    null = true
    type = boolean
  }
  column "is_primary" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_email_address_uid" {
    columns = [column.uid]
  }
  index "UQE_email_address_email" {
    unique  = true
    columns = [column.email]
  }
  index "UQE_email_address_lower_email" {
    unique  = true
    columns = [column.lower_email]
  }
}
table "email_hash" {
  schema = schema.public
  column "hash" {
    null = false
    type = character_varying(32)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.hash]
  }
  index "UQE_email_hash_email" {
    unique  = true
    columns = [column.email]
  }
}
table "external_login_user" {
  schema = schema.public
  column "external_id" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "login_source_id" {
    null = false
    type = bigint
  }
  column "raw_data" {
    null = true
    type = text
  }
  column "provider" {
    null = true
    type = character_varying(25)
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "first_name" {
    null = true
    type = character_varying(255)
  }
  column "last_name" {
    null = true
    type = character_varying(255)
  }
  column "nick_name" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "avatar_url" {
    null = true
    type = text
  }
  column "location" {
    null = true
    type = character_varying(255)
  }
  column "access_token" {
    null = true
    type = text
  }
  column "access_token_secret" {
    null = true
    type = text
  }
  column "refresh_token" {
    null = true
    type = text
  }
  column "expires_at" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.external_id, column.login_source_id]
  }
  index "IDX_external_login_user_provider" {
    columns = [column.provider]
  }
  index "IDX_external_login_user_user_id" {
    columns = [column.user_id]
  }
}
table "follow" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "follow_id" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_follow_created_unix" {
    columns = [column.created_unix]
  }
  index "UQE_follow_follow" {
    unique  = true
    columns = [column.user_id, column.follow_id]
  }
}
table "gpg_key" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "key_id" {
    null = false
    type = character(16)
  }
  column "primary_key_id" {
    null = true
    type = character(16)
  }
  column "content" {
    null = false
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "expired_unix" {
    null = true
    type = bigint
  }
  column "added_unix" {
    null = true
    type = bigint
  }
  column "emails" {
    null = true
    type = text
  }
  column "verified" {
    null    = false
    type    = boolean
    default = false
  }
  column "can_sign" {
    null = true
    type = boolean
  }
  column "can_encrypt_comms" {
    null = true
    type = boolean
  }
  column "can_encrypt_storage" {
    null = true
    type = boolean
  }
  column "can_certify" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_gpg_key_key_id" {
    columns = [column.key_id]
  }
  index "IDX_gpg_key_owner_id" {
    columns = [column.owner_id]
  }
}
table "gpg_key_import" {
  schema = schema.public
  column "key_id" {
    null = false
    type = character(16)
  }
  column "content" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.key_id]
  }
}
table "hook_task" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "hook_id" {
    null = true
    type = bigint
  }
  column "uuid" {
    null = true
    type = character_varying(255)
  }
  column "payload_content" {
    null = true
    type = text
  }
  column "payload_version" {
    null    = true
    type    = integer
    default = 1
  }
  column "event_type" {
    null = true
    type = character_varying(255)
  }
  column "is_delivered" {
    null = true
    type = boolean
  }
  column "delivered" {
    null = true
    type = bigint
  }
  column "is_succeed" {
    null = true
    type = boolean
  }
  column "request_content" {
    null = true
    type = text
  }
  column "response_content" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_hook_task_hook_id" {
    columns = [column.hook_id]
  }
  index "UQE_hook_task_uuid" {
    unique  = true
    columns = [column.uuid]
  }
}
table "issue" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "index" {
    null = true
    type = bigint
  }
  column "poster_id" {
    null = true
    type = bigint
  }
  column "original_author" {
    null = true
    type = character_varying(255)
  }
  column "original_author_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "content" {
    null = true
    type = text
  }
  column "content_version" {
    null    = false
    type    = integer
    default = 0
  }
  column "milestone_id" {
    null = true
    type = bigint
  }
  column "priority" {
    null = true
    type = integer
  }
  column "is_closed" {
    null = true
    type = boolean
  }
  column "is_pull" {
    null = true
    type = boolean
  }
  column "num_comments" {
    null = true
    type = integer
  }
  column "ref" {
    null = true
    type = character_varying(255)
  }
  column "deadline_unix" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "closed_unix" {
    null = true
    type = bigint
  }
  column "is_locked" {
    null    = false
    type    = boolean
    default = false
  }
  column "time_estimate" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_issue_closed_unix" {
    columns = [column.closed_unix]
  }
  index "IDX_issue_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_issue_deadline_unix" {
    columns = [column.deadline_unix]
  }
  index "IDX_issue_is_closed" {
    columns = [column.is_closed]
  }
  index "IDX_issue_is_pull" {
    columns = [column.is_pull]
  }
  index "IDX_issue_milestone_id" {
    columns = [column.milestone_id]
  }
  index "IDX_issue_original_author_id" {
    columns = [column.original_author_id]
  }
  index "IDX_issue_poster_id" {
    columns = [column.poster_id]
  }
  index "IDX_issue_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_issue_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_issue_repo_index" {
    unique  = true
    columns = [column.repo_id, column.index]
  }
}
table "issue_assignees" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "assignee_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_issue_assignees_assignee_id" {
    columns = [column.assignee_id]
  }
  index "IDX_issue_assignees_issue_id" {
    columns = [column.issue_id]
  }
}
table "issue_content_history" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "poster_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "comment_id" {
    null = true
    type = bigint
  }
  column "edited_unix" {
    null = true
    type = bigint
  }
  column "content_text" {
    null = true
    type = text
  }
  column "is_first_created" {
    null = true
    type = boolean
  }
  column "is_deleted" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_issue_content_history_comment_id" {
    columns = [column.comment_id]
  }
  index "IDX_issue_content_history_edited_unix" {
    columns = [column.edited_unix]
  }
  index "IDX_issue_content_history_issue_id" {
    columns = [column.issue_id]
  }
}
table "issue_dependency" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "dependency_id" {
    null = false
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_issue_dependency_issue_dependency" {
    unique  = true
    columns = [column.issue_id, column.dependency_id]
  }
}
table "issue_index" {
  schema = schema.public
  column "group_id" {
    null = false
    type = bigint
  }
  column "max_index" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.group_id]
  }
  index "IDX_issue_index_max_index" {
    columns = [column.max_index]
  }
}
table "issue_label" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "label_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_issue_label_s" {
    unique  = true
    columns = [column.issue_id, column.label_id]
  }
}
table "issue_pin" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "is_pull" {
    null = false
    type = boolean
  }
  column "pin_order" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_issue_pin_s" {
    unique  = true
    columns = [column.repo_id, column.issue_id]
  }
}
table "issue_user" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "is_read" {
    null = true
    type = boolean
  }
  column "is_mentioned" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_issue_user_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_issue_user_uid" {
    columns = [column.uid]
  }
  index "UQE_issue_user_uid_to_issue" {
    unique  = true
    columns = [column.uid, column.issue_id]
  }
}
table "issue_watch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "is_watching" {
    null = false
    type = boolean
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "updated_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_issue_watch_watch" {
    unique  = true
    columns = [column.user_id, column.issue_id]
  }
}
table "label" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "exclusive" {
    null = true
    type = boolean
  }
  column "exclusive_order" {
    null    = true
    type    = integer
    default = 0
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "color" {
    null = true
    type = character_varying(7)
  }
  column "num_issues" {
    null = true
    type = integer
  }
  column "num_closed_issues" {
    null = true
    type = integer
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "archived_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_label_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_label_org_id" {
    columns = [column.org_id]
  }
  index "IDX_label_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_label_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "language_stat" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "commit_id" {
    null = true
    type = character_varying(255)
  }
  column "is_primary" {
    null = true
    type = boolean
  }
  column "language" {
    null = false
    type = character_varying(50)
  }
  column "size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_language_stat_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_language_stat_language" {
    columns = [column.language]
  }
  index "IDX_language_stat_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_language_stat_s" {
    unique  = true
    columns = [column.repo_id, column.language]
  }
}
table "lfs_lock" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "path" {
    null = true
    type = text
  }
  column "created" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_lfs_lock_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_lfs_lock_repo_id" {
    columns = [column.repo_id]
  }
}
table "lfs_meta_object" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "oid" {
    null = false
    type = character_varying(255)
  }
  column "size" {
    null = false
    type = bigint
  }
  column "repository_id" {
    null = false
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_lfs_meta_object_oid" {
    columns = [column.oid]
  }
  index "IDX_lfs_meta_object_repository_id" {
    columns = [column.repository_id]
  }
  index "IDX_lfs_meta_object_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_lfs_meta_object_s" {
    unique  = true
    columns = [column.oid, column.repository_id]
  }
}
table "login_source" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = true
    type = integer
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "is_active" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_sync_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "two_factor_policy" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "cfg" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_login_source_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_login_source_is_active" {
    columns = [column.is_active]
  }
  index "IDX_login_source_is_sync_enabled" {
    columns = [column.is_sync_enabled]
  }
  index "IDX_login_source_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_login_source_name" {
    unique  = true
    columns = [column.name]
  }
}
table "milestone" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "content" {
    null = true
    type = text
  }
  column "is_closed" {
    null = true
    type = boolean
  }
  column "num_issues" {
    null = true
    type = integer
  }
  column "num_closed_issues" {
    null = true
    type = integer
  }
  column "completeness" {
    null = true
    type = integer
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "deadline_unix" {
    null = true
    type = bigint
  }
  column "closed_date_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_milestone_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_milestone_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_milestone_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "mirror" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "interval" {
    null = true
    type = bigint
  }
  column "enable_prune" {
    null    = false
    type    = boolean
    default = true
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "next_update_unix" {
    null = true
    type = bigint
  }
  column "lfs_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "lfs_endpoint" {
    null = true
    type = text
  }
  column "remote_address" {
    null = true
    type = character_varying(2048)
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_mirror_next_update_unix" {
    columns = [column.next_update_unix]
  }
  index "IDX_mirror_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_mirror_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "notice" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = true
    type = integer
  }
  column "description" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_notice_created_unix" {
    columns = [column.created_unix]
  }
}
table "notification" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "status" {
    null = false
    type = smallint
  }
  column "source" {
    null = false
    type = smallint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "commit_id" {
    null = true
    type = character_varying(255)
  }
  column "comment_id" {
    null = true
    type = bigint
  }
  column "updated_by" {
    null = false
    type = bigint
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "updated_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_notification_idx_notification_commit_id" {
    columns = [column.commit_id]
  }
  index "IDX_notification_idx_notification_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_notification_idx_notification_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_notification_idx_notification_source" {
    columns = [column.source]
  }
  index "IDX_notification_idx_notification_status" {
    columns = [column.status]
  }
  index "IDX_notification_idx_notification_updated_by" {
    columns = [column.updated_by]
  }
  index "IDX_notification_idx_notification_user_id" {
    columns = [column.user_id]
  }
  index "IDX_notification_u_s_uu" {
    columns = [column.user_id, column.status, column.updated_unix]
  }
}
table "oauth2_application" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "client_id" {
    null = true
    type = character_varying(255)
  }
  column "client_secret" {
    null = true
    type = character_varying(255)
  }
  column "confidential_client" {
    null    = false
    type    = boolean
    default = true
  }
  column "skip_secondary_authorization" {
    null    = false
    type    = boolean
    default = false
  }
  column "redirect_uris" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_oauth2_application_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_oauth2_application_uid" {
    columns = [column.uid]
  }
  index "IDX_oauth2_application_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_oauth2_application_client_id" {
    unique  = true
    columns = [column.client_id]
  }
}
table "oauth2_authorization_code" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "grant_id" {
    null = true
    type = bigint
  }
  column "code" {
    null = true
    type = character_varying(255)
  }
  column "code_challenge" {
    null = true
    type = character_varying(255)
  }
  column "code_challenge_method" {
    null = true
    type = character_varying(255)
  }
  column "redirect_uri" {
    null = true
    type = character_varying(255)
  }
  column "valid_until" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_oauth2_authorization_code_valid_until" {
    columns = [column.valid_until]
  }
  index "UQE_oauth2_authorization_code_code" {
    unique  = true
    columns = [column.code]
  }
}
table "oauth2_grant" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "application_id" {
    null = true
    type = bigint
  }
  column "counter" {
    null    = false
    type    = bigint
    default = 1
  }
  column "scope" {
    null = true
    type = text
  }
  column "nonce" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_oauth2_grant_application_id" {
    columns = [column.application_id]
  }
  index "IDX_oauth2_grant_user_id" {
    columns = [column.user_id]
  }
  index "UQE_oauth2_grant_user_application" {
    unique  = true
    columns = [column.user_id, column.application_id]
  }
}
table "org_user" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "is_public" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_org_user_is_public" {
    columns = [column.is_public]
  }
  index "IDX_org_user_org_id" {
    columns = [column.org_id]
  }
  index "IDX_org_user_uid" {
    columns = [column.uid]
  }
  index "UQE_org_user_s" {
    unique  = true
    columns = [column.uid, column.org_id]
  }
}
table "package" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "semver_compatible" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_internal" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_lower_name" {
    columns = [column.lower_name]
  }
  index "IDX_package_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_package_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_package_type" {
    columns = [column.type]
  }
  index "UQE_package_s" {
    unique  = true
    columns = [column.owner_id, column.type, column.lower_name]
  }
}
table "package_blob" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "hash_md5" {
    null = false
    type = character(32)
  }
  column "hash_sha1" {
    null = false
    type = character(40)
  }
  column "hash_sha256" {
    null = false
    type = character(64)
  }
  column "hash_sha512" {
    null = false
    type = character(128)
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_blob_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_package_blob_hash_md5" {
    columns = [column.hash_md5]
  }
  index "IDX_package_blob_hash_sha1" {
    columns = [column.hash_sha1]
  }
  index "IDX_package_blob_hash_sha256" {
    columns = [column.hash_sha256]
  }
  index "IDX_package_blob_hash_sha512" {
    columns = [column.hash_sha512]
  }
  index "UQE_package_blob_md5" {
    unique  = true
    columns = [column.hash_md5]
  }
  index "UQE_package_blob_sha1" {
    unique  = true
    columns = [column.hash_sha1]
  }
  index "UQE_package_blob_sha256" {
    unique  = true
    columns = [column.hash_sha256]
  }
  index "UQE_package_blob_sha512" {
    unique  = true
    columns = [column.hash_sha512]
  }
}
table "package_blob_upload" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "bytes_received" {
    null    = false
    type    = bigint
    default = 0
  }
  column "hash_state_bytes" {
    null = true
    type = bytea
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "updated_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_blob_upload_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "package_cleanup_rule" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "owner_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "keep_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "keep_pattern" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "remove_days" {
    null    = false
    type    = integer
    default = 0
  }
  column "remove_pattern" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "match_full_name" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_unix" {
    null    = false
    type    = bigint
    default = 0
  }
  column "updated_unix" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_cleanup_rule_enabled" {
    columns = [column.enabled]
  }
  index "IDX_package_cleanup_rule_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_package_cleanup_rule_type" {
    columns = [column.type]
  }
  index "UQE_package_cleanup_rule_s" {
    unique  = true
    columns = [column.owner_id, column.type]
  }
}
table "package_file" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "version_id" {
    null = false
    type = bigint
  }
  column "blob_id" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "composite_key" {
    null = true
    type = character_varying(255)
  }
  column "is_lead" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_file_blob_id" {
    columns = [column.blob_id]
  }
  index "IDX_package_file_composite_key" {
    columns = [column.composite_key]
  }
  index "IDX_package_file_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_package_file_lower_name" {
    columns = [column.lower_name]
  }
  index "IDX_package_file_version_id" {
    columns = [column.version_id]
  }
  index "UQE_package_file_s" {
    unique  = true
    columns = [column.version_id, column.lower_name, column.composite_key]
  }
}
table "package_property" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "ref_type" {
    null = false
    type = bigint
  }
  column "ref_id" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_property_name" {
    columns = [column.name]
  }
  index "IDX_package_property_ref_id" {
    columns = [column.ref_id]
  }
  index "IDX_package_property_ref_type" {
    columns = [column.ref_type]
  }
}
table "package_version" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "package_id" {
    null = false
    type = bigint
  }
  column "creator_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "lower_version" {
    null = false
    type = character_varying(255)
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "is_internal" {
    null    = false
    type    = boolean
    default = false
  }
  column "metadata_json" {
    null = true
    type = text
  }
  column "download_count" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_package_version_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_package_version_is_internal" {
    columns = [column.is_internal]
  }
  index "IDX_package_version_lower_version" {
    columns = [column.lower_version]
  }
  index "IDX_package_version_package_id" {
    columns = [column.package_id]
  }
  index "UQE_package_version_s" {
    unique  = true
    columns = [column.package_id, column.lower_version]
  }
}
table "project" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "creator_id" {
    null = false
    type = bigint
  }
  column "is_closed" {
    null = true
    type = boolean
  }
  column "board_type" {
    null = true
    type = bigint
  }
  column "card_type" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "closed_date_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_project_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_project_is_closed" {
    columns = [column.is_closed]
  }
  index "IDX_project_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_project_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_project_title" {
    columns = [column.title]
  }
  index "IDX_project_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "project_board" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "default" {
    null    = false
    type    = boolean
    default = false
  }
  column "sorting" {
    null    = false
    type    = integer
    default = 0
  }
  column "color" {
    null = true
    type = character_varying(7)
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "creator_id" {
    null = false
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_project_board_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_project_board_project_id" {
    columns = [column.project_id]
  }
  index "IDX_project_board_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "project_issue" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "project_id" {
    null = true
    type = bigint
  }
  column "project_board_id" {
    null = true
    type = bigint
  }
  column "sorting" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_project_issue_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_project_issue_project_board_id" {
    columns = [column.project_board_id]
  }
  index "IDX_project_issue_project_id" {
    columns = [column.project_id]
  }
}
table "protected_branch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "branch_name" {
    null = true
    type = character_varying(255)
  }
  column "priority" {
    null    = false
    type    = bigint
    default = 0
  }
  column "can_push" {
    null    = false
    type    = boolean
    default = false
  }
  column "enable_whitelist" {
    null = true
    type = boolean
  }
  column "whitelist_user_i_ds" {
    null = true
    type = text
  }
  column "whitelist_team_i_ds" {
    null = true
    type = text
  }
  column "enable_merge_whitelist" {
    null    = false
    type    = boolean
    default = false
  }
  column "whitelist_deploy_keys" {
    null    = false
    type    = boolean
    default = false
  }
  column "merge_whitelist_user_i_ds" {
    null = true
    type = text
  }
  column "merge_whitelist_team_i_ds" {
    null = true
    type = text
  }
  column "can_force_push" {
    null    = false
    type    = boolean
    default = false
  }
  column "enable_force_push_allowlist" {
    null    = false
    type    = boolean
    default = false
  }
  column "force_push_allowlist_user_i_ds" {
    null = true
    type = text
  }
  column "force_push_allowlist_team_i_ds" {
    null = true
    type = text
  }
  column "force_push_allowlist_deploy_keys" {
    null    = false
    type    = boolean
    default = false
  }
  column "enable_status_check" {
    null    = false
    type    = boolean
    default = false
  }
  column "status_check_contexts" {
    null = true
    type = text
  }
  column "enable_approvals_whitelist" {
    null    = false
    type    = boolean
    default = false
  }
  column "approvals_whitelist_user_i_ds" {
    null = true
    type = text
  }
  column "approvals_whitelist_team_i_ds" {
    null = true
    type = text
  }
  column "required_approvals" {
    null    = false
    type    = bigint
    default = 0
  }
  column "block_on_rejected_reviews" {
    null    = false
    type    = boolean
    default = false
  }
  column "block_on_official_review_requests" {
    null    = false
    type    = boolean
    default = false
  }
  column "block_on_outdated_branch" {
    null    = false
    type    = boolean
    default = false
  }
  column "dismiss_stale_approvals" {
    null    = false
    type    = boolean
    default = false
  }
  column "ignore_stale_approvals" {
    null    = false
    type    = boolean
    default = false
  }
  column "require_signed_commits" {
    null    = false
    type    = boolean
    default = false
  }
  column "protected_file_patterns" {
    null = true
    type = text
  }
  column "unprotected_file_patterns" {
    null = true
    type = text
  }
  column "block_admin_merge_override" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_protected_branch_s" {
    unique  = true
    columns = [column.repo_id, column.branch_name]
  }
}
table "protected_tag" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "name_pattern" {
    null = true
    type = character_varying(255)
  }
  column "allowlist_user_i_ds" {
    null = true
    type = text
  }
  column "allowlist_team_i_ds" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
}
table "public_key" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "fingerprint" {
    null = false
    type = character_varying(255)
  }
  column "content" {
    null = false
    type = text
  }
  column "mode" {
    null    = false
    type    = integer
    default = 2
  }
  column "type" {
    null    = false
    type    = integer
    default = 1
  }
  column "login_source_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "verified" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_public_key_fingerprint" {
    columns = [column.fingerprint]
  }
  index "IDX_public_key_owner_id" {
    columns = [column.owner_id]
  }
}
table "pull_auto_merge" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "pull_id" {
    null = true
    type = bigint
  }
  column "doer_id" {
    null = false
    type = bigint
  }
  column "merge_style" {
    null = true
    type = character_varying(30)
  }
  column "message" {
    null = true
    type = text
  }
  column "delete_branch_after_merge" {
    null = true
    type = boolean
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_pull_auto_merge_doer_id" {
    columns = [column.doer_id]
  }
  index "UQE_pull_auto_merge_pull_id" {
    unique  = true
    columns = [column.pull_id]
  }
}
table "pull_request" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = true
    type = integer
  }
  column "status" {
    null = true
    type = integer
  }
  column "conflicted_files" {
    null = true
    type = text
  }
  column "commits_ahead" {
    null = true
    type = integer
  }
  column "commits_behind" {
    null = true
    type = integer
  }
  column "changed_protected_files" {
    null = true
    type = text
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "index" {
    null = true
    type = bigint
  }
  column "head_repo_id" {
    null = true
    type = bigint
  }
  column "base_repo_id" {
    null = true
    type = bigint
  }
  column "head_branch" {
    null = true
    type = character_varying(255)
  }
  column "base_branch" {
    null = true
    type = character_varying(255)
  }
  column "merge_base" {
    null = true
    type = character_varying(64)
  }
  column "allow_maintainer_edit" {
    null    = false
    type    = boolean
    default = false
  }
  column "has_merged" {
    null = true
    type = boolean
  }
  column "merged_commit_id" {
    null = true
    type = character_varying(64)
  }
  column "merger_id" {
    null = true
    type = bigint
  }
  column "merged_unix" {
    null = true
    type = bigint
  }
  column "flow" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_pull_request_base_repo_id" {
    columns = [column.base_repo_id]
  }
  index "IDX_pull_request_has_merged" {
    columns = [column.has_merged]
  }
  index "IDX_pull_request_head_repo_id" {
    columns = [column.head_repo_id]
  }
  index "IDX_pull_request_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_pull_request_merged_unix" {
    columns = [column.merged_unix]
  }
  index "IDX_pull_request_merger_id" {
    columns = [column.merger_id]
  }
}
table "push_mirror" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "remote_name" {
    null = true
    type = character_varying(255)
  }
  column "remote_address" {
    null = true
    type = character_varying(2048)
  }
  column "sync_on_commit" {
    null    = false
    type    = boolean
    default = true
  }
  column "interval" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "last_update" {
    null = true
    type = bigint
  }
  column "last_error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_push_mirror_last_update" {
    columns = [column.last_update]
  }
  index "IDX_push_mirror_repo_id" {
    columns = [column.repo_id]
  }
}
table "reaction" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "comment_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "original_author_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "original_author" {
    null = true
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_reaction_comment_id" {
    columns = [column.comment_id]
  }
  index "IDX_reaction_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_reaction_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_reaction_original_author" {
    columns = [column.original_author]
  }
  index "IDX_reaction_original_author_id" {
    columns = [column.original_author_id]
  }
  index "IDX_reaction_type" {
    columns = [column.type]
  }
  index "IDX_reaction_user_id" {
    columns = [column.user_id]
  }
  index "UQE_reaction_s" {
    unique  = true
    columns = [column.type, column.issue_id, column.comment_id, column.user_id, column.original_author_id, column.original_author]
  }
}
table "release" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "publisher_id" {
    null = true
    type = bigint
  }
  column "tag_name" {
    null = true
    type = character_varying(255)
  }
  column "original_author" {
    null = true
    type = character_varying(255)
  }
  column "original_author_id" {
    null = true
    type = bigint
  }
  column "lower_tag_name" {
    null = true
    type = character_varying(255)
  }
  column "target" {
    null = true
    type = character_varying(255)
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "sha1" {
    null = true
    type = character_varying(64)
  }
  column "num_commits" {
    null = true
    type = bigint
  }
  column "note" {
    null = true
    type = text
  }
  column "is_draft" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_prerelease" {
    null    = false
    type    = boolean
    default = false
  }
  column "is_tag" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_release_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_release_original_author_id" {
    columns = [column.original_author_id]
  }
  index "IDX_release_publisher_id" {
    columns = [column.publisher_id]
  }
  index "IDX_release_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_release_sha1" {
    columns = [column.sha1]
  }
  index "IDX_release_tag_name" {
    columns = [column.tag_name]
  }
  index "UQE_release_n" {
    unique  = true
    columns = [column.repo_id, column.tag_name]
  }
}
table "renamed_branch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "from" {
    null = true
    type = character_varying(255)
  }
  column "to" {
    null = true
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_renamed_branch_repo_id" {
    columns = [column.repo_id]
  }
}
table "repo_archiver" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = integer
  }
  column "status" {
    null = true
    type = integer
  }
  column "commit_id" {
    null = true
    type = character_varying(64)
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_archiver_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_repo_archiver_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_repo_archiver_s" {
    unique  = true
    columns = [column.repo_id, column.type, column.commit_id]
  }
}
table "repo_indexer_status" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "commit_sha" {
    null = true
    type = character_varying(64)
  }
  column "indexer_type" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_indexer_status_s" {
    columns = [column.repo_id, column.indexer_type]
  }
}
table "repo_license" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = false
    type = bigint
  }
  column "commit_id" {
    null = true
    type = character_varying(255)
  }
  column "license" {
    null = false
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_license_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_repo_license_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_repo_license_s" {
    unique  = true
    columns = [column.repo_id, column.license]
  }
}
table "repo_redirect" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "redirect_repo_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_redirect_lower_name" {
    columns = [column.lower_name]
  }
  index "UQE_repo_redirect_s" {
    unique  = true
    columns = [column.owner_id, column.lower_name]
  }
}
table "repo_topic" {
  schema = schema.public
  column "repo_id" {
    null = false
    type = bigint
  }
  column "topic_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.repo_id, column.topic_id]
  }
}
table "repo_transfer" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "doer_id" {
    null = true
    type = bigint
  }
  column "recipient_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "team_i_ds" {
    null = true
    type = text
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  column "updated_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_transfer_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_repo_transfer_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "repo_unit" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = integer
  }
  column "config" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "anonymous_access_mode" {
    null    = false
    type    = integer
    default = 0
  }
  column "everyone_access_mode" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repo_unit_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_repo_unit_s" {
    columns = [column.repo_id, column.type]
  }
}
table "repository" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "owner_name" {
    null = true
    type = character_varying(255)
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = text
  }
  column "website" {
    null = true
    type = character_varying(2048)
  }
  column "original_service_type" {
    null = true
    type = integer
  }
  column "original_url" {
    null = true
    type = character_varying(2048)
  }
  column "default_branch" {
    null = true
    type = character_varying(255)
  }
  column "default_wiki_branch" {
    null = true
    type = character_varying(255)
  }
  column "num_watches" {
    null = true
    type = integer
  }
  column "num_stars" {
    null = true
    type = integer
  }
  column "num_forks" {
    null = true
    type = integer
  }
  column "num_issues" {
    null = true
    type = integer
  }
  column "num_closed_issues" {
    null = true
    type = integer
  }
  column "num_pulls" {
    null = true
    type = integer
  }
  column "num_closed_pulls" {
    null = true
    type = integer
  }
  column "num_milestones" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_closed_milestones" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_projects" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_closed_projects" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_action_runs" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_closed_action_runs" {
    null    = false
    type    = integer
    default = 0
  }
  column "is_private" {
    null = true
    type = boolean
  }
  column "is_empty" {
    null = true
    type = boolean
  }
  column "is_archived" {
    null = true
    type = boolean
  }
  column "is_mirror" {
    null = true
    type = boolean
  }
  column "status" {
    null    = false
    type    = integer
    default = 0
  }
  column "is_fork" {
    null    = false
    type    = boolean
    default = false
  }
  column "fork_id" {
    null = true
    type = bigint
  }
  column "is_template" {
    null    = false
    type    = boolean
    default = false
  }
  column "template_id" {
    null = true
    type = bigint
  }
  column "size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "git_size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "lfs_size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "is_fsck_enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "close_issues_via_commit_in_any_branch" {
    null    = false
    type    = boolean
    default = false
  }
  column "topics" {
    null = true
    type = text
  }
  column "object_format_name" {
    null    = false
    type    = character_varying(6)
    default = "sha1"
  }
  column "trust_model" {
    null = true
    type = integer
  }
  column "avatar" {
    null = true
    type = character_varying(64)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "archived_unix" {
    null    = true
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_repository_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_repository_fork_id" {
    columns = [column.fork_id]
  }
  index "IDX_repository_is_archived" {
    columns = [column.is_archived]
  }
  index "IDX_repository_is_empty" {
    columns = [column.is_empty]
  }
  index "IDX_repository_is_fork" {
    columns = [column.is_fork]
  }
  index "IDX_repository_is_mirror" {
    columns = [column.is_mirror]
  }
  index "IDX_repository_is_private" {
    columns = [column.is_private]
  }
  index "IDX_repository_is_template" {
    columns = [column.is_template]
  }
  index "IDX_repository_lower_name" {
    columns = [column.lower_name]
  }
  index "IDX_repository_name" {
    columns = [column.name]
  }
  index "IDX_repository_original_service_type" {
    columns = [column.original_service_type]
  }
  index "IDX_repository_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_repository_template_id" {
    columns = [column.template_id]
  }
  index "IDX_repository_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_repository_s" {
    unique  = true
    columns = [column.owner_id, column.lower_name]
  }
}
table "review" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = true
    type = integer
  }
  column "reviewer_id" {
    null = true
    type = bigint
  }
  column "reviewer_team_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "original_author" {
    null = true
    type = character_varying(255)
  }
  column "original_author_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "content" {
    null = true
    type = text
  }
  column "official" {
    null    = false
    type    = boolean
    default = false
  }
  column "commit_id" {
    null = true
    type = character_varying(64)
  }
  column "stale" {
    null    = false
    type    = boolean
    default = false
  }
  column "dismissed" {
    null    = false
    type    = boolean
    default = false
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_review_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_review_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_review_reviewer_id" {
    columns = [column.reviewer_id]
  }
  index "IDX_review_updated_unix" {
    columns = [column.updated_unix]
  }
}
table "review_state" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "pull_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "commit_sha" {
    null = false
    type = character_varying(64)
  }
  column "updated_files" {
    null = false
    type = text
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_review_state_pull_id" {
    columns = [column.pull_id]
  }
  index "UQE_review_state_pull_commit_user" {
    unique  = true
    columns = [column.user_id, column.pull_id, column.commit_sha]
  }
}
table "secret" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "repo_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "data" {
    null = true
    type = text
  }
  column "description" {
    null = true
    type = text
  }
  column "created_unix" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_secret_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_secret_repo_id" {
    columns = [column.repo_id]
  }
  index "UQE_secret_owner_repo_name" {
    unique  = true
    columns = [column.owner_id, column.repo_id, column.name]
  }
}
table "session" {
  schema = schema.public
  column "key" {
    null = false
    type = character(16)
  }
  column "data" {
    null = true
    type = bytea
  }
  column "expiry" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.key]
  }
}
table "star" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_star_created_unix" {
    columns = [column.created_unix]
  }
  index "UQE_star_s" {
    unique  = true
    columns = [column.uid, column.repo_id]
  }
}
table "stopwatch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_stopwatch_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_stopwatch_user_id" {
    columns = [column.user_id]
  }
}
table "system_setting" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "setting_key" {
    null = true
    type = character_varying(255)
  }
  column "setting_value" {
    null = true
    type = text
  }
  column "version" {
    null = true
    type = integer
  }
  column "created" {
    null = true
    type = bigint
  }
  column "updated" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_system_setting_setting_key" {
    unique  = true
    columns = [column.setting_key]
  }
}
table "task" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "doer_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = integer
  }
  column "status" {
    null = true
    type = integer
  }
  column "start_time" {
    null = true
    type = bigint
  }
  column "end_time" {
    null = true
    type = bigint
  }
  column "payload_content" {
    null = true
    type = text
  }
  column "message" {
    null = true
    type = text
  }
  column "created" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_task_doer_id" {
    columns = [column.doer_id]
  }
  index "IDX_task_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_task_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_task_status" {
    columns = [column.status]
  }
}
table "team" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "lower_name" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "authorize" {
    null = true
    type = integer
  }
  column "num_repos" {
    null = true
    type = integer
  }
  column "num_members" {
    null = true
    type = integer
  }
  column "includes_all_repositories" {
    null    = false
    type    = boolean
    default = false
  }
  column "can_create_org_repo" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_team_org_id" {
    columns = [column.org_id]
  }
}
table "team_invite" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "token" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "inviter_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "org_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "team_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "email" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_team_invite_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_team_invite_org_id" {
    columns = [column.org_id]
  }
  index "IDX_team_invite_team_id" {
    columns = [column.team_id]
  }
  index "IDX_team_invite_token" {
    columns = [column.token]
  }
  index "IDX_team_invite_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_team_invite_team_mail" {
    unique  = true
    columns = [column.team_id, column.email]
  }
}
table "team_repo" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "team_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_team_repo_org_id" {
    columns = [column.org_id]
  }
  index "UQE_team_repo_s" {
    unique  = true
    columns = [column.team_id, column.repo_id]
  }
}
table "team_unit" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "team_id" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = integer
  }
  column "access_mode" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_team_unit_org_id" {
    columns = [column.org_id]
  }
  index "UQE_team_unit_s" {
    unique  = true
    columns = [column.team_id, column.type]
  }
}
table "team_user" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "org_id" {
    null = true
    type = bigint
  }
  column "team_id" {
    null = true
    type = bigint
  }
  column "uid" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_team_user_org_id" {
    columns = [column.org_id]
  }
  index "UQE_team_user_s" {
    unique  = true
    columns = [column.team_id, column.uid]
  }
}
table "topic" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = true
    type = character_varying(50)
  }
  column "repo_count" {
    null = true
    type = integer
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_topic_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_topic_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_topic_name" {
    unique  = true
    columns = [column.name]
  }
}
table "tracked_time" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "time" {
    null = false
    type = bigint
  }
  column "deleted" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_tracked_time_issue_id" {
    columns = [column.issue_id]
  }
  index "IDX_tracked_time_user_id" {
    columns = [column.user_id]
  }
}
table "two_factor" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = true
    type = bigint
  }
  column "secret" {
    null = true
    type = character_varying(255)
  }
  column "scratch_salt" {
    null = true
    type = character_varying(255)
  }
  column "scratch_hash" {
    null = true
    type = character_varying(255)
  }
  column "last_used_passcode" {
    null = true
    type = character_varying(10)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_two_factor_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_two_factor_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_two_factor_uid" {
    unique  = true
    columns = [column.uid]
  }
}
table "upload" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uuid" {
    null = true
    type = uuid
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "UQE_upload_uuid" {
    unique  = true
    columns = [column.uuid]
  }
}
table "user" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "full_name" {
    null = true
    type = character_varying(255)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "keep_email_private" {
    null = true
    type = boolean
  }
  column "email_notifications_preference" {
    null    = false
    type    = character_varying(20)
    default = "enabled"
  }
  column "passwd" {
    null = false
    type = character_varying(255)
  }
  column "passwd_hash_algo" {
    null    = false
    type    = character_varying(255)
    default = "argon2"
  }
  column "must_change_password" {
    null    = false
    type    = boolean
    default = false
  }
  column "login_type" {
    null = true
    type = integer
  }
  column "login_source" {
    null    = false
    type    = bigint
    default = 0
  }
  column "login_name" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null = true
    type = integer
  }
  column "location" {
    null = true
    type = character_varying(255)
  }
  column "website" {
    null = true
    type = character_varying(255)
  }
  column "rands" {
    null = true
    type = character_varying(32)
  }
  column "salt" {
    null = true
    type = character_varying(32)
  }
  column "language" {
    null = true
    type = character_varying(5)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  column "last_login_unix" {
    null = true
    type = bigint
  }
  column "last_repo_visibility" {
    null = true
    type = boolean
  }
  column "max_repo_creation" {
    null    = false
    type    = integer
    default = -1
  }
  column "is_active" {
    null = true
    type = boolean
  }
  column "is_admin" {
    null = true
    type = boolean
  }
  column "is_restricted" {
    null    = false
    type    = boolean
    default = false
  }
  column "allow_git_hook" {
    null = true
    type = boolean
  }
  column "allow_import_local" {
    null = true
    type = boolean
  }
  column "allow_create_organization" {
    null    = true
    type    = boolean
    default = true
  }
  column "prohibit_login" {
    null    = false
    type    = boolean
    default = false
  }
  column "avatar" {
    null = false
    type = character_varying(2048)
  }
  column "avatar_email" {
    null = false
    type = character_varying(255)
  }
  column "use_custom_avatar" {
    null = true
    type = boolean
  }
  column "num_followers" {
    null = true
    type = integer
  }
  column "num_following" {
    null    = false
    type    = integer
    default = 0
  }
  column "num_stars" {
    null = true
    type = integer
  }
  column "num_repos" {
    null = true
    type = integer
  }
  column "num_teams" {
    null = true
    type = integer
  }
  column "num_members" {
    null = true
    type = integer
  }
  column "visibility" {
    null    = false
    type    = integer
    default = 0
  }
  column "repo_admin_change_team_access" {
    null    = false
    type    = boolean
    default = false
  }
  column "diff_view_style" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "theme" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "keep_activity_private" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_user_is_active" {
    columns = [column.is_active]
  }
  index "IDX_user_last_login_unix" {
    columns = [column.last_login_unix]
  }
  index "IDX_user_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_user_lower_name" {
    unique  = true
    columns = [column.lower_name]
  }
  index "UQE_user_name" {
    unique  = true
    columns = [column.name]
  }
}
table "user_badge" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "badge_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_badge_user_id" {
    columns = [column.user_id]
  }
}
table "user_blocking" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "blocker_id" {
    null = true
    type = bigint
  }
  column "blockee_id" {
    null = true
    type = bigint
  }
  column "note" {
    null = true
    type = character_varying(255)
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_blocking_created_unix" {
    columns = [column.created_unix]
  }
  index "UQE_user_blocking_block" {
    unique  = true
    columns = [column.blocker_id, column.blockee_id]
  }
}
table "user_open_id" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = false
    type = bigint
  }
  column "uri" {
    null = false
    type = character_varying(255)
  }
  column "show" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_open_id_uid" {
    columns = [column.uid]
  }
  index "UQE_user_open_id_uri" {
    unique  = true
    columns = [column.uri]
  }
}
table "user_redirect" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "lower_name" {
    null = false
    type = character_varying(255)
  }
  column "redirect_user_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_redirect_lower_name" {
    columns = [column.lower_name]
  }
  index "UQE_user_redirect_s" {
    unique  = true
    columns = [column.lower_name]
  }
}
table "user_setting" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "setting_key" {
    null = true
    type = character_varying(255)
  }
  column "setting_value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_user_setting_setting_key" {
    columns = [column.setting_key]
  }
  index "IDX_user_setting_user_id" {
    columns = [column.user_id]
  }
  index "UQE_user_setting_key_userid" {
    unique  = true
    columns = [column.user_id, column.setting_key]
  }
}
table "version" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "version" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
}
table "watch" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "mode" {
    null    = false
    type    = smallint
    default = 1
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_watch_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_watch_updated_unix" {
    columns = [column.updated_unix]
  }
  index "UQE_watch_watch" {
    unique  = true
    columns = [column.user_id, column.repo_id]
  }
}
table "webauthn_credential" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "lower_name" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "credential_id" {
    null = true
    type = bytea
  }
  column "public_key" {
    null = true
    type = bytea
  }
  column "attestation_type" {
    null = true
    type = character_varying(255)
  }
  column "aaguid" {
    null = true
    type = bytea
  }
  column "sign_count" {
    null = true
    type = bigint
  }
  column "clone_warning" {
    null = true
    type = boolean
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_webauthn_credential_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_webauthn_credential_credential_id" {
    columns = [column.credential_id]
  }
  index "IDX_webauthn_credential_updated_unix" {
    columns = [column.updated_unix]
  }
  index "IDX_webauthn_credential_user_id" {
    columns = [column.user_id]
  }
  index "UQE_webauthn_credential_s" {
    unique  = true
    columns = [column.lower_name, column.user_id]
  }
}
table "webhook" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "repo_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "is_system_webhook" {
    null = true
    type = boolean
  }
  column "url" {
    null = true
    type = text
  }
  column "http_method" {
    null = true
    type = character_varying(255)
  }
  column "content_type" {
    null = true
    type = integer
  }
  column "secret" {
    null = true
    type = text
  }
  column "events" {
    null = true
    type = text
  }
  column "is_active" {
    null = true
    type = boolean
  }
  column "type" {
    null = true
    type = character_varying(16)
  }
  column "meta" {
    null = true
    type = text
  }
  column "last_status" {
    null = true
    type = integer
  }
  column "header_authorization_encrypted" {
    null = true
    type = text
  }
  column "created_unix" {
    null = true
    type = bigint
  }
  column "updated_unix" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_webhook_created_unix" {
    columns = [column.created_unix]
  }
  index "IDX_webhook_is_active" {
    columns = [column.is_active]
  }
  index "IDX_webhook_owner_id" {
    columns = [column.owner_id]
  }
  index "IDX_webhook_repo_id" {
    columns = [column.repo_id]
  }
  index "IDX_webhook_updated_unix" {
    columns = [column.updated_unix]
  }
}
schema "public" {
  comment = "standard public schema"
}
